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
from pathlib import Path

from jitabi.templates import hash_templates

from .cpython import c_source_from_abi as c_source_from_abi

import jitabi.codegen.cpython as _cpython
import jitabi.protocol as _protocol


def hash_pipeline(as_bytes: bool = True) -> bytes | str:
    '''
    Return a sha256 hash of all things affecting C sources generation code.

    '''
    hasher = hashlib.sha256()
    hasher.update(hash_templates(as_bytes=True))
    hasher.update(Path(_cpython.__file__).read_bytes())
    hasher.update(Path(_protocol.__file__).read_bytes())

    return (
        hasher.digest() if as_bytes
        else hasher.hexdigest()
    )
