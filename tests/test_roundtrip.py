import os
import json
import logging

import pytest
from hypothesis import (
    event,
    given,
    settings,
    strategies as st,
    HealthCheck
)
from antelope_rs.testing import AntelopeDebugEncoder

from jitabi._testing import (
    default_max_examples,
    default_batch_size,
    default_test_deadline,
    iter_type_meta,
)


logger = logging.getLogger(__name__)


max_examples = int(os.getenv('JITABI_MAX_EXAMPLES', default_max_examples))

EXAMPLE_QUOTA = int(os.environ['JITABI_EXAMPLE_QUOTA'])
BATCH_SIZE = min(max_examples, default_batch_size)
ROUNDS = (EXAMPLE_QUOTA + BATCH_SIZE - 1) // BATCH_SIZE


@pytest.mark.parametrize("batch", range(ROUNDS))
@pytest.mark.parametrize(
    'case_info',
    iter_type_meta(),
    indirect=True,
    ids=lambda p: f'{p[0]}:{p[2]}',
)
@given(rng=st.randoms())
@settings(
    max_examples=BATCH_SIZE,
    deadline=default_test_deadline,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_roundtrip(case_info, batch, rng, memory_guard):
    '''
    For this single (ABI, type) do example_quota round-trip checks.

    '''
    mod_name, abi, _, module, type_name = case_info

    case_name = f'{mod_name}:{type_name}:{batch}'

    pack_fn = getattr(module, f'pack_{type_name}')
    unpack_fn = getattr(module, f'unpack_{type_name}')

    input_value = abi.random_of(type_name, rng=rng)
    logger.debug(
        f'Generated input for {case_name}: %s',
        json.dumps(input_value, indent=4, cls=AntelopeDebugEncoder)
    )

    packed = pack_fn(input_value)

    logger.debug(f'Packed {case_name} into {len(packed):,} bytes.')

    unpacked = unpack_fn(packed)

    logger.debug(
        f'Unpacked {case_name}: %s',
        json.dumps(unpacked, indent=4, cls=AntelopeDebugEncoder)
    )

    event(case_name)

    abi.assert_deep_eq(type_name, input_value, unpacked)

    logger.debug(f'Roundtrip passed for {case_name}!')


@pytest.mark.parametrize(
    'case_info',
    iter_type_meta(),
    indirect=True,
    ids=lambda p: f'roundtrip-dispatch-{p[0]}:{p[2]}',
)
@given(rng=st.randoms())
@settings(
    max_examples=1,
    deadline=default_test_deadline,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_roundtrip_distpach(case_info, rng):
    mod_name, abi, _, module, type_name = case_info

    case_name = f'{mod_name}:{type_name}'

    input_value = abi.random_of(type_name, rng=rng)
    logger.debug(
        f'Generated input for {case_name}: %s',
        json.dumps(input_value, indent=4, cls=AntelopeDebugEncoder)
    )

    packed = module.pack(type_name, input_value)
    rs_packed = abi.pack(type_name, input_value)

    assert packed == rs_packed

    logger.debug(f'Packed {case_name} into {len(packed):,} bytes.')

    unpacked = module.unpack(type_name, packed)
    rs_unpacked = abi.unpack(type_name, rs_packed)

    logger.debug(
        f'Unpacked {case_name}: %s',
        json.dumps(unpacked, indent=4, cls=AntelopeDebugEncoder)
    )

    event(case_name)

    abi.assert_deep_eq(type_name, input_value, unpacked)
    abi.assert_deep_eq(type_name, input_value, rs_unpacked)

    logger.debug(f'Roundtrip passed for {case_name}!')


