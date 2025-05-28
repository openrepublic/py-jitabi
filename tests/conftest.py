from __future__ import annotations

import os
import gc
import time
import struct

from multiprocessing import (
    shared_memory,
    resource_tracker
)

import psutil
import pytest
from jitabi import JITContext
from jitabi._testing import (
    testing_cache_dir,
    default_max_examples,
    default_abi_whitelist_str,
    load_abis,
    bootstrap_cache
)

try:
    import pdbp

except ImportError:
    ...


_MEM_THRESHOLD = float(os.getenv('MEM_EXIT_THRESHOLD', '75'))
_GC_MEM_THRESHOLD = float(os.getenv('MEM_GC_THRESHOLD', '40'))


# store a native-endian float64 in a shared memory segment in order for
# _maybe_gc logic to be shared across xdist workers

# set in pytest_configure
_GC_SHM: shared_memory.SharedMemory | None = None
# native-endian float64
_PACK = struct.Struct('d')


def _read_last_gc_time() -> float:
    '''
    Return the shared float (seconds epoch).

    '''
    return _PACK.unpack_from(_GC_SHM.buf, 0)[0]


def _write_last_gc_time(ts: float) -> None:
    '''
    Store *ts* into the shared segment.

    '''
    _PACK.pack_into(_GC_SHM.buf, 0, ts)


_GC_INTERVAL = 30.0  # min seconds between GC runs


def _maybe_gc(usage_pct: float) -> None:
    '''
    Compare current time against shared float, if delta >= _GC_INTERVAL return.

    Else check current system memory usage % and if its over _GC_MEM_THRESHOLD
    trigger gc collection and write current time to shared float segment.

    '''
    now = time.time()
    if now - _read_last_gc_time() < _GC_INTERVAL:
        return

    if usage_pct >= _GC_MEM_THRESHOLD:
        gc.collect()
        _write_last_gc_time(now)


def _abort_on_low_mem(usage_pct: float) -> None:
    '''
    If current system memory usage % is over _MEM_THRESHOLD trigger test
    session exit.

    '''
    if usage_pct >= _MEM_THRESHOLD:
        pytest.exit(
            (
                f'system memory usage is {usage_pct:.1f}% '
                f'(threshold: {_MEM_THRESHOLD}%), exiting.'
            ),
            returncode=99,
        )


def _apply_mem_guards() -> None:
    usage_pct = psutil.virtual_memory().percent
    _maybe_gc(usage_pct)
    _abort_on_low_mem(usage_pct)


@pytest.fixture
def memory_guard() -> None:
    '''
    Abort the test session when overall RAM usage >= threshold.

    Executed before *and* after every test invocation, which means
    once per Hypothesis example.

    '''
    _apply_mem_guards()
    yield
    _apply_mem_guards()


def pytest_configure(config: pytest.Config) -> None:
    '''
    * Controller:
        - compile ABIs once
    * Worker:
        - use workerinput['workercount'] / workerid to compute its
          share and set JIT_EXAMPLE_QUOTA accordingly

    '''
    global _GC_SHM

    force_reload: bool = bool(os.getenv('JITABI_RELOAD', ''))
    abi_whitelist: list[str] = os.getenv(
        'JITABI_WHITELIST',default_abi_whitelist_str
    ).split(',')

    total = int(os.getenv('JITABI_MAX_EXAMPLES', default_max_examples))
    workers = int(os.environ.get('PYTEST_XDIST_WORKER_COUNT', '1'))
    quota = (total + workers - 1) // workers
    os.environ['JITABI_EXAMPLE_QUOTA'] = str(quota)

    if not hasattr(config, 'workerinput'):
        # we are the controller
        _GC_SHM = shared_memory.SharedMemory(create=True, size=8)
        _write_last_gc_time(time.time())          # initialise
        # make the name available to workers
        os.environ['JITABI_GC_SHM_NAME'] = _GC_SHM.name

        bootstrap_cache(
            abis=load_abis(whitelist=abi_whitelist),
            force_reload=force_reload
        )

    else:
        shm_name = os.environ['JITABI_GC_SHM_NAME']
        _GC_SHM = shared_memory.SharedMemory(name=shm_name)
        resource_tracker.unregister(_GC_SHM._name, 'shared_memory')


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    '''
    Cleanup shared float segment

    '''
    if _GC_SHM is not None:
        _GC_SHM.close()
        if (
            not hasattr(session.config, 'workerinput')
            or
            'PYTEST_XDIST_WORKER_COUNT' not in os.environ
        ):
            _GC_SHM.unlink()


@pytest.fixture(scope='session')
def jit_ctx():
    # readonly=True -> never triggers a compile, only imports from disk
    return JITContext(
        cache_path=testing_cache_dir,
        readonly=True,
        ipc_locked=False
    )

@pytest.fixture
def case_info(request, jit_ctx):
    '''
    Turn the lightweight triple (mod, abi_path, tname) into the full 5-tuple
    used by the tests.  **Runs once per test instance**, not at collection.

    '''
    mod_name, abi, type_name = request.param
    key, module = jit_ctx.module_for_abi(mod_name, abi)
    return mod_name, abi, key, module, type_name
