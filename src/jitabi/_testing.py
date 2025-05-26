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
import logging
from types import ModuleType
from pathlib import Path
from typing import Iterator

from deepdiff import DeepDiff

from jitabi import JITContext
from jitabi.utils import JSONHexEncoder, normalize_dict
from jitabi.cache import CacheKey

from jitabi.protocol import (
    TypeModifier,
    IOTypes,
    is_raw_type,
    is_std_type,
    ABIDef,
    SHIPABIDef,
    ABIView
)


logger = logging.getLogger(__name__)


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



def random_abi_type(
    abi: ABIView,
    type_name: str,
    min_list_size: int = 0,
    max_list_size: int = 2,
    list_delta: int = 0,
    chance_of_none: float = 0.5,
    chance_delta: float = 0.5,
    type_args: dict[str, dict] = {},
    rng: random.Random  = random
) -> IOTypes:
    # get type meta like alias solve & modifier extraction
    resolved = abi.resolve_type(type_name)
    res_type = resolved.resolved_name

    # keyword args for potential recursive invocation
    kwargs = {
        'min_list_size': min_list_size,
        'max_list_size': max_list_size,
        'list_delta': list_delta,
        'chance_of_none': chance_of_none,
        'chance_delta': chance_delta,
        'type_args': type_args,
        'rng': rng
    }

    # if we have an entry for this type in type_args override args with it
    if type_name in type_args:
        kwargs |= type_args[type_name]

    # handle modifiers
    match resolved.modifier:
        case TypeModifier.ARRAY:
            # decrease next levels list sizes by list_delta or clamp to 0
            pre_min_size = kwargs['min_list_size']
            pre_max_size = kwargs['max_list_size']
            kwargs['min_list_size'] = max(
                kwargs['min_list_size'] - kwargs['list_delta'], 0
            )
            kwargs['max_list_size'] = max(
                kwargs['max_list_size'] - kwargs['list_delta'], 0
            )
            # calculate a random list size for this level & generate
            list_size = rng.randint(pre_min_size, pre_max_size)
            return [
                random_abi_type(abi, res_type, **kwargs)
                for _ in range(list_size)
            ]

        case TypeModifier.OPTIONAL | TypeModifier.EXTENSION:
            # maybe generate a None
            if rng.random() < 1. - chance_of_none:
                return None

            # increase next level's chances of None by chance_delta or clamp to
            # 100% chance == 1.
            kwargs['chance_of_none'] = min(
                1.,
                chance_of_none + chance_delta
            )

            # generate type
            return random_abi_type(abi, res_type, **kwargs)

    # check for raw(LEN) types
    if is_raw_type(res_type):
        return random_std_type('raw(' + resolved.args[0] + ')', rng=rng)

    # delegate standard types
    if is_std_type(res_type):
        return random_std_type(res_type, rng=rng)

    if res_type in abi.variant_map:
        # if type resolved to an enum choose a random variant of it
        enum_type = rng.choice(
            abi.variant_map[res_type].types
        )
        # generate the variant obj
        obj = random_abi_type(
            abi,
            enum_type,
            **kwargs
        )
        if isinstance(obj, dict):
            # if its a struct variant inject type key
            return {
                'type': enum_type,
                **obj
            }

        # variant is a std type, just return
        return obj

    # by this point we expect types to be a struct defined in the ABI
    if res_type not in abi.struct_map:
        raise TypeError(
            f'Expected {type_name} to resolve to a struct!: {resolved}'
        )

    # get struct meta
    struct = abi.struct_map[res_type]

    # if struct has a base, generate it first
    base = (
        {} if not struct.base
        else random_abi_type(
            abi,
            struct.base,
            **kwargs
        )
    )

    # generate actual struct obj from its fields
    obj = base | {
        f.name: random_abi_type(
            abi,
            f.type_,
            **kwargs
        )
        for f in struct.fields
    }

    # when object contains fields with the extension modifier ($) we must
    # ensure that after the first None field, all remaining extension fields
    # are also None
    found_extension = False
    for field, value in zip(struct.fields, list(obj.values())):
        if field.type_[-1] == '$' and not value:
            found_extension = True

        if found_extension:
            obj[field.name] = None

    return obj


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


def load_abis(whitelist: list[str] = _default_abi_whitelist) -> list[tuple[str, ABIView]]:
    abis = []
    for p in testing_abi_dir.iterdir():
        if (
            p.is_file()
            and p.suffix == '.json'
            and p.stem in whitelist
        ):
            cls = ABIDef
            if p.stem == 'standard':
                cls = SHIPABIDef

            logger.info(f'Loading ABI: {p.stem} using {cls.__name__}')

            try:
                abis.append((
                    p.stem, ABIView.from_abi(cls.from_file(p))
                ))

            except Exception as e:
                logger.error(f'While loading {p}')
                raise

    return abis


def bootstrap_cache(
    abis: list[str, ABIView] = load_abis(),
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
    tuple[str, ABIView, CacheKey, ModuleType, str]
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
        for s in abi.structs + abi.variants:
            # if no type_whitelist or not whitelisted skip
            if '*' not in type_whitelist and s.name not in type_whitelist:
                continue

            # yield a test case
            yield mod_name, abi, key, module, s.name


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
