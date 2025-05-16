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
import hashlib

from enum import Enum
from typing import Protocol, runtime_checkable


# base types which module.c.j2 already has serialization functions for
STD_TYPES = [
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
]


# extra structs added to all abi modules
DEFAULT_STRUCTS = [
    {
      'name': 'asset',
      'fields': [
        {
          'name': 'amount',
          'type': 'int64'
        },
        {
          'name': 'symbol',
          'type': 'symbol'
        }
      ]
    },
    {
      'name': 'extended_asset',
      'fields': [
        {
          'name': 'quantity',
          'type': 'asset'
        },
        {
          'name': 'contract',
          'type': 'name'
        }
      ]
    },
]


# extra aliases added to all abi modules
DEFAULT_ALIASES = [
    ('float128', 'raw(16)'),
    ('name', 'uint64'),
    ('account_name', 'uint64'),
    ('symbol', 'uint64'),
    ('symbol_code', 'uint64'),
    ('rd160', 'raw(20)'),
    ('checksum160', 'raw(20)'),
    ('sha256', 'raw(32)'),
    ('checksum256', 'raw(32)'),
    ('checksum512', 'raw(64)'),
    ('time_point', 'uint64'),
    ('time_point_sec', 'uint32'),
    ('block_timestamp_type', 'uint32'),
    ('public_key', 'raw(34)'),
    ('signature', 'raw(66)'),
]


# generate a hash of all the default types which is used as seed for all
# abi view hashes, that way if std types change, we will get a different hash
h = hashlib.sha256()

for std_type in STD_TYPES:
    h.update(std_type.encode())

for struct_def in DEFAULT_STRUCTS:
    h.update(struct_def['name'].encode())
    if struct_def.get('base'):
        h.update(struct_def['base'].encode())
    for field in struct_def['fields']:
        h.update(field['name'].encode())
        h.update(field['type'].encode())

for new_type, from_type in DEFAULT_ALIASES:
    h.update(new_type.encode())
    h.update(from_type.encode())


DEFAULT_HASH = h.digest()


# ABIView protocol

class TypeModifier(Enum):
    NONE = 0,
    ARRAY = 1,
    OPTIONAL = 2,
    EXTENSION = 3


@runtime_checkable
class AliasDef(Protocol):
    def new_type_name(self) -> str:
        ...

    def from_type_name(self) -> str:
        ...


@runtime_checkable
class EnumDef(Protocol):
    def name(self) -> str:
        ...


    def variants(self) -> list[str]:
        ...


@runtime_checkable
class FieldDef(Protocol):
    def name(self) -> str:
        ...

    def type_name(self) -> str:
        ...


@runtime_checkable
class StructDef(Protocol):
    def name(self) -> str:
        ...

    def base(self) -> str:
        ...

    def fields(self) -> list[FieldDef]:
        ...


@runtime_checkable
class ABIView(Protocol):
    def aliases(self) -> list[AliasDef]:
        ...

    def enums(self) -> list[EnumDef]:
        ...

    def structs(self) -> list[StructDef]:
        ...


def hash_abi_view(abi: ABIView) -> str:
    '''
    Get a sha256 of the types definition

    '''
    h = hashlib.sha256()

    h.update(DEFAULT_HASH)

    h.update(b'structs')
    for s in abi.structs():
        h.update(s.name().encode())
        for f in s.fields():
            h.update(f.name().encode())
            h.update(f.type_name().encode())

    h.update(b'enums')
    for e in abi.enums():
        h.update(e.name().encode())
        for v in e.variants():
            h.update(v.encode())

    h.update(b'aliases')
    for a in abi.aliases():
        h.update(a.new_type_name().encode())
        h.update(a.from_type_name().encode())

    return h.hexdigest()
