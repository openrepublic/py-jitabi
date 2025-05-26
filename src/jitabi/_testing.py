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
import json
import random
import string
import weakref
from types import ModuleType
from pathlib import Path
from typing import Iterator

from deepdiff import DeepDiff

from jitabi import JITContext
from jitabi.json import ABI
from jitabi.utils import JSONHexEncoder, normalize_dict
from jitabi.cache import CacheKey


inside_ci = any(
    os.getenv(v)
    for v in [
        'CI', 'GITHUB_ACTIONS', 'GITLAB_CI', 'TRAVIS', 'CIRCLECI'
    ]
)


_LETTERS = string.ascii_letters


def _randbits(rng, bits: int) -> int:
    return rng.getrandbits(bits)


def _rand(rng) -> float:
    return rng.random()


def _randbytes(rng, n: int) -> bytes:
    return rng.randbytes(n)


def _signed_int(rng, bits: int) -> int:
    val = _randbits(rng, bits)
    sign_bit = 1 << (bits - 1)
    return val - (sign_bit << 1) if val & sign_bit else val


def _make_generators(rng) -> dict[str, callable[[], object]]:
    '''
    Build a fresh dispatch table that closes over *rng*.

    Called exactly once per unique RNG thanks to the cache below.
    '''
    return {
        # booleans
        'bool': lambda: bool(_randbits(rng, 1)),

        # unsigned ints
        **{f'uint{b}': (lambda b=b: _randbits(rng, b))
           for b in (8, 16, 32, 64, 128)},

        # signed ints
        **{f'int{b}': (lambda b=b: _signed_int(rng, b))
           for b in (8, 16, 32, 64, 128)},

        # LEB128 helpers
        'varuint32': lambda: _randbits(rng, 32),
        'varint32': lambda: _signed_int(rng, 32),

        # floats in small ranges
        'float32': lambda: _rand(rng) * 2.0 - 1.0,
        'float64': lambda: _rand(rng) * 2.0e4 - 1.0e4,

        # blobs & ASCII strings
        'bytes': lambda: _randbytes(rng, _randbits(rng, 4) & 0x0F),
        'string': lambda: ''.join(
            rng.choices(
                _LETTERS,
                k=(_randbits(rng, 4) & 0x0C) | _randbits(rng, 2)
            )
        ),
    }


# RNG-aware cache
_GLOBAL_GENERATORS = _make_generators(random)

_GEN_CACHE: 'weakref.WeakKeyDictionary[random.Random, dict[str, callable]]'
_GEN_CACHE = weakref.WeakKeyDictionary()


def _generators_for(rng) -> dict[str, callable[[], object]]:
    '''
    Return the dispatch table for *rng*, building it once if necessary.
    '''
    if rng is random:  # stdlib’s singleton module
        return _GLOBAL_GENERATORS

    try:
        return _GEN_CACHE[rng]
    except KeyError:
        table = _make_generators(rng)
        _GEN_CACHE[rng] = table
        return table


def random_std_type(
    type_name: str,
    *,
    rng: random.Random | None = None
):
    '''
    Generate a random value for *type_name* using *rng*.

    Parameters
    ----------
    type_name : str
        Any supported std type (e.g. 'uint64', 'float32') or 'raw(N)'.
    rng : random.Random | None
        Source of randomness.  Defaults to the stdlib global RNG.
    '''
    rng = rng or random

    if type_name.startswith('raw(') and type_name.endswith(')'):
        size = int(type_name[4:-1])
        return _randbytes(rng, size)

    generators = _generators_for(rng)
    try:
        return generators[type_name]()
    except KeyError:
        raise TypeError(f'Unknown standard type “{type_name}”') from None


def assert_dict_eq(a: dict, b: dict):
    a = normalize_dict(a)
    b = normalize_dict(b)
    diff = DeepDiff(
        a,
        b,
        ignore_order=True,
        ignore_encoding_errors=True,
        significant_digits=1,
    )
    if diff:
        dump = json.dumps(diff, indent=4, cls=JSONHexEncoder)
        raise AssertionError(f'Differences found: {dump}')


# stuff used in our tests

default_max_examples: int = 10 if inside_ci else 100
default_test_deadline: int = 5 * 60 * 1000  # 5 min in ms

# abi jsons on tests/abis
_default_abi_whitelist: list[str] = [
    'test_abi',
    'eosio_token',
    'eosio_system',
    'standard',
]

default_abi_whitelist_str: str = ','.join(_default_abi_whitelist)

tests_dir = Path(__file__).parent.parent.parent / 'tests'
testing_abi_dir = tests_dir / 'abis'
testing_cache_dir =  tests_dir / '.pytest-jitabi'


def load_abis(whitelist: list[str] = _default_abi_whitelist) -> list[tuple[str, ABI]]:
    return [
        (p.stem, ABI.from_file(p))
        for p in testing_abi_dir.iterdir()
        if (
            p.is_file()
            and p.suffix == '.json'
            and p.stem in whitelist
        )
    ]


def bootstrap_cache(
    abis: list[str, ABI] = load_abis(),
    cache_path: Path = testing_cache_dir,
    force_reload: bool = False
) -> None:
    '''
    Instantiate all ABIs modules once in order to trigger compilation of any
    missing ones.

    '''
    ctx = JITContext(cache_path=cache_path)
    for mod_name, abi in abis:
        ctx.module_for_abi(mod_name, abi, force_reload=force_reload)


def iter_type_cases() -> Iterator[
    tuple[str, ABI, CacheKey, ModuleType, str]
]:
    '''
    Yield (mod_name, abi, cache_key, module, type_name) for every struct / enum.

    '''

    # load whitelisted abis
    abi_whitelist: list[str] = os.getenv(
        'JITABI_WHITELIST',
        default_abi_whitelist_str
    ).split(',')
    abis = load_abis(whitelist=abi_whitelist)

    # maybe get type whitelist, * should signal no whitelist
    type_whitelist: set[str] = set(
        os.getenv('JITABI_TYPE_WHITELIST', '*').split(',')
    )

    # load the actual CPython modules for each abi (should of been built during
    # `pytest_configure` hook)
    jit = JITContext(
        cache_path=testing_cache_dir,
        readonly=True
    )
    modules: dict[str, ModuleType] = {
        mod_name: jit.module_for_abi(mod_name, abi)
        for mod_name, abi in abis
    }

    # for every abi
    for mod_name, abi in abis:
        key, module = modules[mod_name]
        # for every struct or enum
        for s in abi.structs() + abi.enums():
            tname = s.name()
            # if no type_whitelist or not whitelisted skip
            if '*' not in type_whitelist and tname not in type_whitelist:
                continue

            # yield a test case
            yield mod_name, abi, key, module, tname


def measure_leaks_in_call(
    trials: int,
    fn: callable,
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
    before: int | None = None
    for trial in range(trials):
        if not before:
            # warm up gc cache by doing one call exactly before measuring
            # for larger *args this seems to fix argument passing gc ref noise
            fn(*args)
            before = sys.gettotalrefcount()

        fn(*args)

    after = sys.gettotalrefcount()
    # if refs are negative no way we leak
    ref_delta = max(after - before, 0)
    return ref_delta
