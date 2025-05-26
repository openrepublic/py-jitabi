from __future__ import annotations

import os

import pytest

from jitabi._testing import (
    default_abi_whitelist_str,
    load_abis,
    bootstrap_cache
)

try:
    import pdbp

except ImportError:
    ...


def pytest_configure(config: pytest.Config) -> None:
    '''
    * Controller:
        - compile ABIs once
    * Worker:
        - use workerinput['workercount'] / workerid to compute its
          share and set JIT_EXAMPLE_QUOTA accordingly

    '''
    force_reload: bool = bool(os.getenv('JITABI_RELOAD', ''))
    abi_whitelist: list[str] = os.getenv(
        'JITABI_WHITELIST',default_abi_whitelist_str
    ).split(',')

    if not hasattr(config, 'workerinput'):
        # we are the controller
        bootstrap_cache(
            abis=load_abis(whitelist=abi_whitelist),
            force_reload=force_reload
        )
