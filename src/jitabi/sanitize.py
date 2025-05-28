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
Helpers for validation of ABIView names & types, helping ensure no injections
can happen.

'''
import re

from typing import Annotated

from msgspec import Meta

from jitabi.utils import is_raw_type


_ID_PATTERN = r'^[A-Za-z_][A-Za-z0-9_]*$'
_ID_RE = re.compile(_ID_PATTERN)

_TYPE_PATTERN = r'^([A-Za-z_][A-Za-z0-9_]*)(?:\[\]|\?|\$)*$'
_TYPE_RE = re.compile(_TYPE_PATTERN)

_TYPE_ALLOW_EMPTY_PATTERN = r'^(?:$|([A-Za-z_][A-Za-z0-9_]*)(\[\]|\?|\$)?)$'

_ANTELOPE_NAME_PATTERN = r'^(?:$|[A-Za-z_][A-Za-z0-9_\.]*)$'

def check_ident(name: str, what: str, allow_raw: bool = False):
    '''
    Make sure `name` is a safe C identifier or raise ValueError.
    `what` is used for a helpful error message.

    '''
    if _ID_RE.match(name):
        return

    if allow_raw and is_raw_type(name):
        return

    raise ValueError(f'{what} "{name}" is not a valid C identifier')


def check_type(type_name: str):
    '''
    Validate `bool`, `uint32`, `my_struct[]`, `bytes?`, `name$`, etc

    '''
    if not _TYPE_RE.match(type_name):
        raise ValueError(f'type "{type_name}" is not a valid ABI type syntax')


BaseTypeName = Annotated[
    str,
    Meta(
        pattern=_TYPE_ALLOW_EMPTY_PATTERN,
        min_length=0,
        max_length=128
    )
]


TypeName = Annotated[
    str,
    Meta(
        pattern=_TYPE_PATTERN,
        min_length=1,
        max_length=128
    )
]

FieldName = Annotated[
    str,
    Meta(
        pattern=_ID_PATTERN,
        min_length=1,
        max_length=128
    )
]

AntelopeName = Annotated[
    str,
    Meta(
        pattern=_ANTELOPE_NAME_PATTERN,
        min_length=0,
        max_length=13
    )
]
