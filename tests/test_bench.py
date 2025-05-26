import os
import pytest

from jitabi import JITContext
from jitabi.json import ABI
from jitabi._testing import (
    inside_ci,
    assert_dict_eq,
    testing_cache_dir,
    testing_abi_dir
)


if 'PYTEST_XDIST_WORKER' in os.environ:
    pytest.skip(
        'benchmark module cant be run with xdist',
        allow_module_level=True
    )

if inside_ci:
    pytest.skip(
        'benchmark cant be run on CI',
        allow_module_level=True
    )


max_time: float = 2 * 60
stdabi = ABI.from_file(testing_abi_dir / 'standard.json')
jit = JITContext(cache_path=testing_cache_dir)


_, std = jit.module_for_abi(
    'standard', stdabi,
)

_, std_no_inline = jit.module_for_abi(
    'standard_noinline', stdabi,
    params={'inlined': False},
)


# generate fat block
input_fat_sample = stdabi.random_of(
    'signed_block',
    type_args={
        'transaction_receipt[]': {
            'min_list_size': 10_000,
            'max_list_size': 10_000,
        },
        'signature[]': {
            'min_list_size': 1,
            'max_list_size': 1
        }
    }
)
packed_fat_sample: bytes = std.pack_signed_block(input_fat_sample)


# generate empty block
input_sample = stdabi.random_of(
    'signed_block',
    type_args={
        'transaction_receipt[]': {
            'min_list_size': 0,
            'max_list_size': 0,
        },
    }
)
packed_sample: bytes = std.pack_signed_block(input_sample)


@pytest.mark.benchmark(
    group='fat_block_decoding',
    max_time=max_time,
    disable_gc=True
)
@pytest.mark.parametrize(
    'module',
    (
        std,
        std_no_inline
    ),
    ids=(
        'default',
        'non-inlined',
    )
)
def test_unpack_fat_block(benchmark, module):
    '''
    Using different module compile time params, benchmark decoding of
    signed_block payloads.

    '''
    # run benchmark
    unpacked = benchmark(
        module.unpack_signed_block,
        packed_fat_sample
    )

    # sanity check
    assert_dict_eq(input_fat_sample, unpacked)


@pytest.mark.benchmark(
    group='empty_block_decoding',
    max_time=max_time,
    disable_gc=True
)
@pytest.mark.parametrize(
    'module',
    (
        std,
        std_no_inline
    ),
    ids=(
        'default',
        'non-inlined',
    )
)
def test_unpack_empty_block(benchmark, module):
    '''
    Using different module compile time params, benchmark decoding of
    signed_block payloads.

    '''
    # run benchmark
    unpacked = benchmark(
        module.unpack_signed_block,
        packed_sample
    )

    # sanity check
    assert_dict_eq(input_sample, unpacked)
