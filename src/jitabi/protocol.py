# py-jitabi: Create JIT compiled CPython modules from antelope protocol ABIs
# Copyright 2025-eternity Guillermo Rodriguez

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from __future__ import annotations

import hashlib

from enum import Enum
from pathlib import Path

import msgspec

from frozendict import frozendict
from msgspec import (
    Struct,
    field,
    to_builtins,
)

from jitabi.utils import is_raw_type
from jitabi.sanitize import (
    AntelopeName,
    BaseTypeName,
    TypeName,
    FieldName
)


# input/output types, these are valid inputs for pack_* & valid outputs for
# unpack_*
IOTypes = (
    bool | int | float | bytes | str | list | dict
)


# base types which module.c.j2 already has serialization functions for
STD_TYPES = set([
    'bool',
    'uint8',
    'uint16',
    'uint32',
    'uint64',
    'uint128',
    'int8',
    'int16',
    'int32',
    'int64',
    'int128',
    'varuint32',
    'varint32',
    'float32',
    'float64',
    'bytes',
    'string',
])


def extract_type_params(name: str) -> list[str]:
    params_start = name.find('(') + 1
    params_end = name.rfind(')')

    if params_end <= params_start:
        raise TypeError(f'Can not extract any params from {name}')

    return (
        name[params_start:params_end]
            .replace(' ', '')
            .split(',')
    )


def is_std_type(name: str) -> bool:
    return name in STD_TYPES


class TypeModifier(Enum):
    NONE = 0,
    ARRAY = 1,
    OPTIONAL = 2,
    EXTENSION = 3


class AliasDef(Struct, frozen=True):
    new_type_name: TypeName
    type_: TypeName = field(name='type')


class VariantDef(Struct, frozen=True):
    name: TypeName
    types: list[TypeName]


class FieldDef(Struct, frozen=True):
    name: FieldName
    type_: TypeName = field(name='type')


class StructDef(Struct, frozen=True):
    name: TypeName
    fields: list[FieldDef]
    base: BaseTypeName | None = None


class ActionDef(Struct, frozen=True):
    name: AntelopeName
    type_: TypeName = field(name='type')
    ricardian_contract: str


class TableDef(Struct, frozen=True):
    name: AntelopeName
    key_names: list[FieldName]
    key_types: list[TypeName]
    index_type: TypeName
    type_: TypeName = field(name='type')


class SHIPTableDef(Struct, frozen=True):
    name: str
    key_names: list[FieldName]
    type_: TypeName = field(name='type')


class ClauseDef(Struct, frozen=True):
    id: str
    body: str


class ErrorMessageDef(Struct, frozen=True):
    error_code: int
    error_msg: str

class ActionResultDef(Struct, frozen=True):
    name: AntelopeName
    result_type: TypeName


class ABIDef(Struct, frozen=True):
    '''
    Msgspec compatible AntelopeIO ABI definition

    See AntelopeIO/leap abi_def.hpp:
        - https://github.com/AntelopeIO/leap/blob/92b6fec5e949660bae78e90ebf555fe71ab06940/libraries/chain/include/eosio/chain/abi_def.hpp

    '''
    version: str
    types: list[AliasDef]
    structs: list[StructDef]
    variants: list[VariantDef] = []

    abi_extensions: list = []
    actions: list[ActionDef] = []
    tables: list[TableDef] = []
    ricardian_clauses: list[ClauseDef] = []
    error_messages: list[ErrorMessageDef] = []
    action_results: list[ActionResultDef] = []

    @staticmethod
    def from_str(s: str) -> ABIDef:
        return msgspec.json.decode(s, type=ABIDef)

    @staticmethod
    def from_file(p: Path | str) -> ABIDef:
        return ABIDef.from_str(
            Path(p).read_text()
        )

    def as_dict(self) -> dict:
        return to_builtins(self)

    def as_bytes(self) -> bytes:
        return msgspec.json.encode(self)


class SHIPABIDef(Struct, frozen=True):
    '''
    Specific ABI definition used by SHIP plugin as first message of websocket
    session.

    '''
    version: str
    structs: list[StructDef]
    types: list[AliasDef]
    variants: list[VariantDef] = []
    tables: list[SHIPTableDef] = []

    @staticmethod
    def from_str(s: str) -> SHIPABIDef:
        return msgspec.json.decode(s, type=SHIPABIDef)

    @staticmethod
    def from_file(p: Path | str) -> SHIPABIDef:
        return SHIPABIDef.from_str(
            Path(p).read_text()
        )

    def as_dict(self) -> dict:
        return to_builtins(self)

    def as_bytes(self) -> bytes:
        return msgspec.json.encode(self)


# builtin types
# see: https://github.com/AntelopeIO/leap/blob/92b6fec5e949660bae78e90ebf555fe71ab06940/libraries/chain/abi_serializer.cpp#L89

# extra structs added to all abi modules
BUILTIN_STRUCTS: frozendict[TypeName, StructDef] = frozendict({
    s['name']: msgspec.convert(s, type=StructDef)
    for s in [
        {
            'name': 'asset',
            'fields': [
                {'name': 'amount', 'type': 'int64'},
                {'name': 'symbol', 'type': 'symbol'}
            ]
        },
        {
            'name': 'extended_asset',
            'fields': [
                {'name': 'quantity', 'type': 'asset'},
                {'name': 'contract', 'type': 'name'}
            ]
        },
    ]
})

# extra aliases added to all abi modules
BUILTIN_ALIASES: frozendict[TypeName, str] = frozendict({
    'float128': 'raw(16)',
    'name': 'uint64',
    'account_name': 'uint64',
    'symbol': 'uint64',
    'symbol_code': 'uint64',
    'rd160': 'raw(20)',
    'checksum160': 'raw(20)',
    'sha256': 'raw(32)',
    'checksum256': 'raw(32)',
    'checksum512': 'raw(64)',
    'time_point': 'uint64',
    'time_point_sec': 'uint32',
    'block_timestamp_type': 'uint32',
    'public_key': 'raw(34)',
    'signature': 'raw(66)',
})


class ABIResolvedType(Struct, frozen=True):
    '''
    Return type of ABIView.resolve_type, contains metadata about an ABI type

    '''
    original_name: TypeName
    resolved_name: str
    args: list[str]
    is_std: bool
    modifier: TypeModifier


class ABIView:

    _def: ABIDef | SHIPABIDef

    alias_map: frozendict[TypeName, TypeName]
    variant_map: frozendict[TypeName, VariantDef]
    struct_map: frozendict[TypeName, StructDef]
    valid_types: frozenset[TypeName]

    def __init__(
        self,
        definition: ABIDef | SHIPABIDef
    ):
        self._def = definition

        alias_map = {
            a.new_type_name: a.type_
            for a in definition.types
        }
        alias_map.update(BUILTIN_ALIASES)

        variant_map = {
            e.name: e
            for e in definition.variants
        }

        struct_map = {
            s.name: s
            for s in definition.structs
        }
        struct_map.update(BUILTIN_STRUCTS)

        self.alias_map = frozendict(alias_map)
        self.struct_map = frozendict(struct_map)
        self.variant_map = frozendict(variant_map)
        self.valid_types = frozenset([
            *STD_TYPES,
            *list(struct_map.keys()),
            *list(variant_map.keys()),
            *list(alias_map.keys()),
        ])

    @staticmethod
    def from_str(s: str) -> ABIView:
        return ABIView(ABIDef.from_str(s))

    @staticmethod
    def from_file(p: Path | str, cls: str | None = None) -> ABIView:
        if not cls:
            cls = ABIDef

        if isinstance(cls, str):
            if cls in ['std', 'standard']:
                cls = SHIPABIDef

            else:
                cls = ABIDef

        return ABIView(cls.from_file(p))

    @staticmethod
    def from_abi(abi: ABIDef | SHIPABIDef | ABIView) -> ABIView:
        if isinstance(abi, ABIView):
            return abi

        return ABIView(abi)

    @property
    def definition(self) -> ABIDef:
        return self._def

    @property
    def structs(self) -> list[StructDef]:
        return self._def.structs

    @property
    def types(self) -> list[AliasDef]:
        return self._def.types

    @property
    def variants(self) -> list[VariantDef]:
        return self._def.variants

    def is_valid_type(self, name: str) -> bool:
        return (
            name in self.valid_types
            or
            is_raw_type(name)
        )

    def maybe_resolve_alias(self, name: str) -> str | None:
        return self.alias_map.get(name, None)

    def resolve_type(self, name: str) -> ABIResolvedType:
        maybe_resolved = self.maybe_resolve_alias(name)
        if maybe_resolved:
            resolved = self.resolve_type(maybe_resolved)
            return ABIResolvedType(
                original_name=name,
                resolved_name=resolved.resolved_name,
                args=resolved.args,
                is_std=resolved.is_std,
                modifier=resolved.modifier
            )

        og_name = name

        args: list[str] = []
        if is_raw_type(name):
            args = extract_type_params(name)
            name = 'raw'

        unmod_name, modifier = maybe_extract_type_mods(name)

        if not self.is_valid_type(unmod_name):
            raise TypeError(
                f'{og_name}(resolved: {unmod_name}) not a valid type!:\n'
                f'{self.valid_types}'
            )

        return ABIResolvedType(
            original_name=og_name,
            resolved_name=unmod_name,
            args=args,
            is_std=is_std_type(unmod_name),
            modifier=modifier
        )

    def hash(self, *, as_bytes: bool = False) -> str | bytes:
        '''
        Get a sha256 of the types definition

        '''
        h = hashlib.sha256()

        h.update(b'structs')
        for s in self._def.structs:
            h.update(s.name.encode())
            for f in s.fields:
                h.update(f.name.encode())
                h.update(f.type_.encode())

        h.update(b'enums')
        for e in self._def.variants:
            h.update(e.name.encode())
            for v in e.types:
                h.update(v.encode())

        h.update(b'aliases')
        for a in self._def.types:
            h.update(a.new_type_name.encode())
            h.update(a.type_.encode())

        return (
            h.digest() if as_bytes
            else h.hexdigest()
        )


def maybe_extract_type_mods(name: str) -> tuple[str, TypeModifier]:
    if name.endswith('[]'):  # array
        return name[:-2], TypeModifier.ARRAY

    if name[-1] == '?':
        return name[:-1], TypeModifier.OPTIONAL

    elif name[-1] == '$':
        return name[:-1], TypeModifier.EXTENSION

    return name, TypeModifier.NONE
