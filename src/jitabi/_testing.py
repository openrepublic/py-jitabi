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
from pathlib import Path

from deepdiff import DeepDiff

from jitabi import JITContext
from jitabi.utils import JSONHexEncoder, normalize_dict

from jitabi.protocol import (
    TypeModifier,
    IOTypes,
    is_raw_type,
    is_std_type,
    solve_cls_alias,
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


_suffixes: dict[TypeModifier, str] = {
    TypeModifier.ARRAY: '[]',
    TypeModifier.OPTIONAL: '?',
    TypeModifier.EXTENSION: '$',
}

def _rest_type_string(base: str, mods: list[TypeModifier]) -> str:
    '''
    Re-constitute the inner-type string by appending the remaining
    modifier suffixes (inner-most first -> rightmost).

    '''
    for m in reversed(mods):
        base += _suffixes[m]
    return base

def random_abi_type(
    abi: ABIView,
    type_name: str,
    *,
    min_list_size: int = 0,
    max_list_size: int = 2,
    list_delta: int = 0,
    chance_of_none: float = 0.5,
    chance_delta: float = 0.5,
    type_args: dict[str, dict] = {},
    rng: random.Random = random,
) -> IOTypes:
    '''
    Generate a random value that is valid for *type_name* according to *abi*,
    honouring **all** trailing modifiers ( `[]`, `?`, `$` ) in the correct
    outer-to-inner order.

    '''
    resolved = abi.resolve_type(type_name)

    # kwargs that may change as we peel modifiers
    kwargs = {
        'min_list_size': min_list_size,
        'max_list_size': max_list_size,
        'list_delta': list_delta,
        'chance_of_none': chance_of_none,
        'chance_delta': chance_delta,
        'type_args': type_args,
        'rng': rng
    }

    # override via *type_args*
    if type_name in type_args:
        kwargs |= type_args[type_name]

    # start with the full modifier chain (outer -> inner)
    modifiers = list(resolved.modifiers)
    base_type = resolved.resolved_name

    # check if a raw was resolved and rebuild base_type
    is_raw = is_raw_type(base_type)
    if is_raw and len(resolved.args) == 1:
        base_type = f'raw({resolved.args[0]})'

    # handle array / optional / extension layers iteratively
    while modifiers:
        outer = modifiers.pop(0)

        if outer is TypeModifier.ARRAY:
            # shrink bounds for deeper arrays
            pre_min = kwargs['min_list_size']
            pre_max = kwargs['max_list_size']
            kwargs['min_list_size'] = max(pre_min - kwargs['list_delta'], 0)
            kwargs['max_list_size'] = max(pre_max - kwargs['list_delta'], 0)

            size = rng.randint(pre_min, pre_max)
            inner = _rest_type_string(base_type, modifiers)
            return [
                random_abi_type(abi, inner, **kwargs)
                for _ in range(size)
            ]

        if outer in (TypeModifier.OPTIONAL, TypeModifier.EXTENSION):
            # decide whether to produce None
            if rng.random() < kwargs['chance_of_none']:
                return None

            # raise None-probability for deeper optionals
            kwargs['chance_of_none'] = min(
                1.0,
                kwargs['chance_of_none'] + kwargs['chance_delta']
            )
            inner = _rest_type_string(base_type, modifiers)
            return random_abi_type(abi, inner, **kwargs)

        # unreachable: only array / optional / extension exist
        raise AssertionError(f'unknown modifier {outer!r}')

    # no more modifiers - generate concrete data
    if is_raw or is_std_type(base_type):
        return random_std_type(base_type, rng=rng)

    # variant
    if base_type in abi.variant_map:
        variant_type = rng.choice(abi.variant_map[base_type].types)
        val = random_abi_type(abi, variant_type, **kwargs)
        return {'type': variant_type, **val} if isinstance(val, dict) else val

    # struct
    if base_type not in abi.struct_map:
        raise TypeError(f'Expected {type_name} to resolve to a struct')

    struct = abi.struct_map[base_type]

    # recurse into base struct first
    obj = (
        {} if not struct.base
        else random_abi_type(abi, struct.base, **kwargs)
    )

    # populate fields
    obj |= {
        f.name: random_abi_type(abi, f.type_, **kwargs)
        for f in struct.fields
    }

    # enforce "$" (binary-extension) rule:
    found_ext = False
    for f in struct.fields:
        if f.type_.endswith('$'):
            if found_ext or obj[f.name] is None:
                found_ext = True
                obj[f.name] = None
        elif found_ext:
            obj[f.name] = None

    return obj


# stuff used in our tests

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

            cls = solve_cls_alias(p.stem)

            logger.info(f'Loading ABI: {p.stem} using {cls.__name__}')

            try:
                abis.append((
                    p.stem, ABIView.from_file(p, cls=cls)
                ))

            except Exception:
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
