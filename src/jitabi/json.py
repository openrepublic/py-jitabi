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
'''
Reference ABIView implementation for JSON defined ABIs

'''
from __future__ import annotations

import json
import random

from pathlib import Path
from dataclasses import dataclass

import jitabi
from jitabi.protocol import (
    IOTypes,
    STD_TYPES,
    is_raw_type,
    is_std_type,
    extract_type_params,
    DEFAULT_ALIASES as ABC_DEFAULT_ALIASES,
    DEFAULT_STRUCTS as ABC_DEFAULT_STRUCTS,
    TypeModifier,
    ABIResolvedType,
    ABIView,
    maybe_extract_type_mods,
)


@dataclass
class ABIAlias:
    alias_def: dict

    def new_type_name(self) -> str:
        return self.alias_def.get('new_type_name')

    def from_type_name(self) -> str:
        return self.alias_def.get('type')


DEFAULT_ALIASES = [
    ABIAlias(alias_def={
        'new_type_name': new_type,
        'type': from_type
    })
    for new_type, from_type in ABC_DEFAULT_ALIASES.items()
]

@dataclass
class ABIEnum:
    enum_def: dict

    def name(self) -> str:
        return self.enum_def.get('name')

    def variants(self) -> list[str]:
        return self.enum_def.get('types')


@dataclass
class ABIField:
    field_def: dict

    def name(self) -> str:
        return self.field_def.get('name')

    def type_name(self) -> str:
        return self.field_def.get('type')


@dataclass
class ABIStruct:
    struct_def: dict

    def name(self) -> str:
        return self.struct_def.get('name')

    def base(self) -> str:
        return self.struct_def.get('base')

    def fields(self) -> list[ABIField]:
        return [
            ABIField(field_def=f)
            for f in self.struct_def.get('fields')
        ]


DEFAULT_STRUCTS = [
    ABIStruct(struct_def=s)
    for s in ABC_DEFAULT_STRUCTS
]


class ABI(ABIView):
    abi_def: dict
    filetype: str = 'json'

    struct_map: dict[str, ABIStruct]

    def __init__(
        self,
        abi_def: dict
    ):
        self.abi_def = abi_def
        self._aliases = [
            ABIAlias(alias_def=a)
            for a in self.abi_def.get('types')
        ] + DEFAULT_ALIASES

        self._enums = [
            ABIEnum(enum_def=e)
            for e in self.abi_def.get('variants')
        ]

        self._enum_dict = {
            e.name(): e
            for e in self._enums
        }

        self._structs = [
            ABIStruct(struct_def=s)
            for s in self.abi_def.get('structs')
        ] + DEFAULT_STRUCTS

        self.struct_map = {
            s.name(): s for s in self._structs
        }

        self._valid_types = set([
            *STD_TYPES,
            *list(self.struct_map.keys()),
            *list(self._enum_dict.keys()),
            *[a.new_type_name() for a in self._aliases],
        ])

    def aliases(self) -> list[ABIAlias]:
        return self._aliases

    def enums(self) -> list[ABIEnum]:
        return self._enums

    def structs(self) -> list[ABIStruct]:
        return self._structs

    def valid_types(self) -> set[str]:
        return self._valid_types

    def is_valid_type(self, name: str) -> bool:
        return (
            is_std_type(name)
            or
            is_raw_type(name)
            or
            name in self._valid_types
        )

    def is_enum_type(self, name: str) -> bool:
        return name in self._enum_dict

    def is_struct_type(self, name: str) -> bool:
        return name in self.struct_map

    def maybe_resolve_alias(self, name: str) -> str | None:
        for a in self.aliases():
            if a.new_type_name() == name:
                return a.from_type_name()

        return None

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
            raise TypeError(f'{og_name} not a valid type!:\n{self._valid_types}')

        return ABIResolvedType(
            original_name=og_name,
            resolved_name=unmod_name,
            args=args,
            is_std=is_std_type(unmod_name),
            modifier=modifier
        )

    @staticmethod
    def from_str(abi_str: str) -> ABI:
        return ABI(abi_def=json.loads(abi_str))

    @staticmethod
    def from_file(path: str | Path) -> ABI:
        return ABI.from_str(Path(path).read_text())

    def as_str(self) -> str:
        return json.dumps(self.abi_def, indent=4)
