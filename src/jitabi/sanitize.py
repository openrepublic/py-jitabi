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

_ID_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_TYPE_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)(\[\]|\?|\$)?$')


def check_ident(name: str, what: str):
    '''
    Make sure `name` is a safe C identifier or raise ValueError.
    `what` is used for a helpful error message.

    '''
    if not _ID_RE.match(name):
        raise ValueError(f'{what} "{name}" is not a valid C identifier')


def check_type(type_name: str):
    '''
    Validate `bool`, `uint32`, `my_struct[]`, `bytes?`, `name$`, etc

    '''
    if not _TYPE_RE.match(type_name):
        raise ValueError(f'type "{type_name}" is not a valid ABI type syntax')
