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
    strategies as st,
    HealthCheck
)
from antelope_rs.testing import AntelopeDebugEncoder
from jitabi._testing import (
    inside_ci,
    default_max_examples,
    default_batch_size,
    default_test_deadline,
    measure_leaks_in_call,
    iter_type_meta,
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


max_examples = int(os.getenv('JITABI_MAX_EXAMPLES', default_max_examples))
trials: int = int(os.getenv('JITABI_TRIALS', str(10)))

EXAMPLE_QUOTA = int(os.environ['JITABI_EXAMPLE_QUOTA'])
BATCH_SIZE = min(max_examples, default_batch_size)
ROUNDS = (EXAMPLE_QUOTA + BATCH_SIZE - 1) // BATCH_SIZE


@pytest.mark.parametrize('round', range(ROUNDS))
@pytest.mark.parametrize(
    'case_info',
    iter_type_meta(),
    indirect=True,
    ids=lambda p: f'{p[0]}:{p[2]}',
)
@given(rng=st.randoms())
@settings(
    max_examples=BATCH_SIZE,
    # avoid shrink phase cause it will always report flaky due to gc & error handling
    phases=[Phase.generate, Phase.target, Phase.explain],
    deadline=default_test_deadline,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_ref_leaks(case_info, round, rng, memory_guard):
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
    mod_name, abi, _, module, type_name = case_info

    case_name = f'{mod_name}:{type_name}:{round}'

    event(case_name)

    pack_fn = getattr(module, f'pack_{type_name}')
    unpack_fn = getattr(module, f'unpack_{type_name}')

    input_value = abi.random_of(type_name, rng=rng)

    logger.debug(
        'Generated input: %s',
        json.dumps(input_value, indent=4, cls=AntelopeDebugEncoder)
    )

    # pack
    delta = measure_leaks_in_call(trials, pack_fn, input_value)
    assert delta == 0, f'{mod_name}.pack_{type_name} leaked {delta} refs!'

    # unpack
    input_raw = pack_fn(input_value)
    delta = measure_leaks_in_call(trials, unpack_fn, input_raw)
    assert delta == 0, f'{mod_name}.unpack_{type_name} leaked {delta} refs!'
