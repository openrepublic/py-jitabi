import os
import json
import logging

import pytest
from hypothesis import (
    event,
    given,
    settings,
    strategies as st
)

from jitabi.utils import JSONHexEncoder
from jitabi._testing import (
    assert_dict_eq,
    default_max_examples,
    default_test_deadline,
    iter_type_cases,
    random_abi_type
)


logger = logging.getLogger(__name__)


max_examples = int(os.getenv('JITABI_MAX_EXAMPLES', default_max_examples))


@pytest.mark.parametrize('case_info', iter_type_cases())
@given(rng=st.randoms())
@settings(max_examples=max_examples, deadline=default_test_deadline)
def test_roundtrip(case_info, rng):
    '''
    For this single (ABI, type) do example_quota round-trip checks.

    '''
    mod_name, abi, key, module, type_name = case_info

    case_name = f'{mod_name}:{type_name}'

    pack_fn = getattr(module, f'pack_{type_name}')
    unpack_fn = getattr(module, f'unpack_{type_name}')

    input_value = random_abi_type(abi, type_name, rng=rng)
    logger.debug(
        f'Generated input for {case_name}: %s',
        json.dumps(input_value, indent=4, cls=JSONHexEncoder)
    )

    packed = pack_fn(input_value)

    logger.debug(f'Packed {case_name} into {len(packed):,} bytes.')

    unpacked = unpack_fn(packed)

    event(case_name)

    assert_dict_eq(input_value, unpacked)

    logger.debug(f'Roundtrip passed for {case_name}!')
