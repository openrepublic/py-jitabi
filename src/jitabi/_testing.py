'''
Fast, test-oriented generators for Antelope “std” types with RNG-aware cache.

* `random_std_type(type_name, rng=<Random>)`
  – deterministic if you supply your own `random.Random`.

The dispatch table for a given RNG is built at most **once** and then looked
up from `_GEN_CACHE` (a `weakref.WeakKeyDictionary`).  The default global RNG
gets its own immutable table `_GLOBAL_GENERATORS`.

'''

from __future__ import annotations

import os
import sys
import logging
from typing import Callable
from pathlib import Path

from jitabi import JITContext

from antelope_rs import (
    ABIView,
)

from antelope_rs.testing import (
    inside_ci
)


logger = logging.getLogger(__name__)


default_max_examples: int = 10 if inside_ci else 100
default_batch_size: int = 100
default_test_deadline: int = 5 * 60 * 1000  # 5 min in ms

# abi jsons on tests/abis
_default_abi_whitelist: list[str] = [
    'test_abi',
    'eosio_msig',
    'eosio_token',
    'eosio_system',
    'standard',
]

default_abi_whitelist_str: str = ','.join(_default_abi_whitelist)

tests_dir = Path(__file__).parent.parent.parent / 'tests'
testing_abi_dir = tests_dir / 'abis'
testing_cache_dir =  tests_dir / '.pytest-jitabi'


def load_abis(whitelist: list[str] = _default_abi_whitelist) -> list[tuple[str, ABIView]]:
    abis = []
    for p in testing_abi_dir.iterdir():
        if (
            p.is_file()
            and p.suffix == '.json'
            and p.stem in whitelist
        ):
            if p.stem not in whitelist:
                continue

            logger.info(f'Loading ABI: {p.stem}')

            try:
                abis.append((
                    p.stem, ABIView.from_file(p, cls=p.stem)
                ))

            except Exception:
                logger.error(f'While loading {p}')
                raise

    return abis


def bootstrap_cache(
    abis: list[tuple[str, ABIView]] = load_abis(),
    cache_path: Path = testing_cache_dir,
    force_reload: bool = False
) -> None:
    '''
    Instantiate all ABIs modules once in order to trigger compilation of any
    missing ones.

    '''
    ctx = JITContext(
        cache_path=cache_path,
        ipc_locked=False
    )
    for mod_name, abi in abis:
        ctx.module_for_abi(mod_name, abi, force_reload=force_reload)


def iter_type_meta():
    '''
    Yield (mod_name, abi, type_name)

    '''
    abi_whitelist = os.getenv(
        'JITABI_WHITELIST', default_abi_whitelist_str
    ).split(',')

    for p in testing_abi_dir.iterdir():
        if p.suffix != '.json' or p.stem not in abi_whitelist:
            continue

        mod_name = p.stem
        abi = ABIView.from_file(p, cls=mod_name)

        for t in abi.structs + abi.variants:
            tname = t.name
            type_whitelist = set(
                os.getenv('JITABI_TYPE_WHITELIST', '*').split(',')
            )
            if '*' not in type_whitelist and tname not in type_whitelist:
                continue

            yield mod_name, abi, tname


def measure_leaks_in_call(
    trials: int,
    fn: Callable,
    *args,
) -> int:
    '''
    Call `fn` in a for loop `trials` times and measure total ref count between
    all the calls.

    Requires a CPython interpreter built with --with-pydebug flag, which
    exposes `sys.gettotalrefcount` function which allows us to track amount of
    global references in the GC system.

    In order to reduce gc noise on results, we avoid doing the first ref measure
    until we are already inside the for loop and after doing a warm up call.

    Its posible to get -1 in `ref_delta` but that never indicates a ref leak so
    we clamp the result to the >= 0 range.

    '''
    before: int = 0
    for _ in range(trials):
        if before == 0:
            # warm up gc cache by doing one call exactly before measuring
            # for larger *args this seems to fix argument passing gc ref noise
            fn(*args)
            before = sys.gettotalrefcount()

        fn(*args)

    after = sys.gettotalrefcount()
    # if refs are negative no way we leak
    ref_delta = max(after - before, 0)
    return ref_delta
