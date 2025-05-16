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

from pathlib import Path
from dataclasses import dataclass

from jitabi.protocol import ABIView


@dataclass
class ABIAlias:
    alias_def: dict

    def new_type_name(self) -> str:
        return self.alias_def.get('new_type_name')

    def from_type_name(self) -> str:
        return self.alias_def.get('type')


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


@dataclass
class ABI(ABIView):
    abi_def: dict

    @staticmethod
    def from_str(abi_str: str) -> ABI:
        return ABI(abi_def=json.loads(abi_str))

    @staticmethod
    def from_file(path: Path) -> ABI:
        with open(path, 'r') as f:
            return ABI(abi_def=json.load(f))


    def aliases(self) -> list[ABIAlias]:
        return [
            ABIAlias(alias_def=a)
            for a in self.abi_def.get('types')
        ]

    def enums(self) -> list[ABIEnum]:
        return [
            ABIEnum(enum_def=e)
            for e in self.abi_def.get('variants')
        ]

    def structs(self) -> list[ABIStruct]:
        return [
            ABIStruct(struct_def=s)
            for s in self.abi_def.get('structs')
        ]
