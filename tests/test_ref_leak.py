import os
import sys
import json
import logging

import pytest
from hypothesis import (
    Phase,
    event,
    given,
    settings,
    strategies as st
)

from jitabi.utils import JSONHexEncoder
from jitabi._testing import (
    inside_ci,
    default_max_examples,
    default_test_deadline,
    measure_leaks_in_call,
    iter_type_cases,
    random_abi_type
)


if inside_ci:
    pytest.skip(
        'leak test cant be run on CI',
        allow_module_level=True
    )

if not hasattr(sys, 'gettotalrefcount'):
    pytest.skip(
        'leak test requires sys.gettotalrefcount '
        '(only available in debug CPython builds)',
        allow_module_level=True
    )


logger = logging.getLogger(__name__)


# total function calls made is:
#     abi_type_count * max_examples * trials * 2
#           244      *     100      *  1000  * 2 = 48_800_000

max_examples = int(os.getenv('JITABI_MAX_EXAMPLES', default_max_examples))
trials: int = int(os.getenv('JITABI_TRIALS', str(100)))


@pytest.mark.parametrize('case_info', iter_type_cases())
@given(rng=st.randoms())
@settings(
    # avoid shrink phase cause it will always report flaky due to gc & error handling
    phases=[Phase.generate, Phase.target, Phase.explain],
    max_examples=max_examples,
    deadline=default_test_deadline
)
def test_ref_leaks(case_info, rng):
    '''
    Auto detect generated extension modules ref leaks.

    Requires a CPython interpreter built with --with-pydebug flag, which
    exposes `sys.gettotalrefcount` function which allows us to track amount of
    global references in the GC system.

    For each ABI in whitelist, for each enum or struct type, run the
    `pack/unpack` functions from the extension module `trials` times, measuring
    the total amount of refs in GC, ensuring the reference delta between all
    the function calls is 0.

    '''
    mod_name, abi, key, module, type_name = case_info

    case_name = f'{mod_name}:{type_name}'

    event(case_name)

    pack_fn = getattr(module, f'pack_{type_name}')
    unpack_fn = getattr(module, f'unpack_{type_name}')

    input_value = random_abi_type(abi, type_name, rng=rng)

    logger.debug(
        'Generated input: %s',
        json.dumps(input_value, indent=4, cls=JSONHexEncoder)
    )

    # pack
    delta = measure_leaks_in_call(trials, pack_fn, input_value)
    assert delta == 0, f'{mod_name}.pack_{type_name} leaked {delta} refs!'

    # unpack
    input_raw = pack_fn(input_value)
    delta = measure_leaks_in_call(trials, unpack_fn, input_raw)
    assert delta == 0, f'{mod_name}.unpack_{type_name} leaked {delta} refs!'
