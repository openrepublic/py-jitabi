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
Filesystem‑backed cache for generated ABI C sources and their compiled extension modules.

Each cache entry is stored under `<cache_root>/<module_name>/<src_hash>/` with two
artifacts:

* `<module_name>.c`: the generated C source.
* `<module_name><EXT_SUFFIX>`: the compiled Python extension.

The :class:`Cache` class keeps an in‑memory mirror of those artifacts to avoid
hitting the filesystem more than necessary, but it always persists updates to
disk so that subsequent interpreter sessions can reuse them.

'''
from __future__ import annotations

import logging
import sysconfig

from types import ModuleType
from ctypes import (
    CDLL,
    PyDLL,
    c_void_p,
    py_object
)
from ctypes.util import find_library
from pathlib import Path
from dataclasses import dataclass


logger = logging.getLogger(__name__)


DEFAULT_CACHE_PATH = Path.home() / '.jitabi'


# `EXT_SUFFIX` is the platform‑specific extension for C extension modules
# (e.g. `.so` on Linux, `.pyd` on Windows).
EXT_SUFFIX = sysconfig.get_config_var('EXT_SUFFIX')


# (module_name, source_hash)
CacheKey = tuple[str, str]

_libname = (
    find_library('dl')
    or
    find_library('c')
    or
    'libc.so.6'
)

libdl = CDLL(_libname)
libdl.dlclose.argtypes = [c_void_p]

def import_module(
    mod_name: str,
    mod_path: Path,
) -> tuple[PyDLL, ModuleType]:
    # https://stackoverflow.com/questions/8295555/how-to-reload-a-python3-c-extension-module
    logger.debug(f'Importing module {mod_name} from {mod_path}')

    shared_lib = PyDLL(mod_path)

    init_fn = getattr(shared_lib, f'PyInit_{mod_name}')
    init_fn.argypes = []
    init_fn.restype = py_object

    return shared_lib, init_fn()


@dataclass
class CacheEntry:
    source: str | None
    shared_lib: PyDLL | None
    module: ModuleType | None

    @staticmethod
    def default() -> CacheEntry:
        return CacheEntry(
            source=None,
            shared_lib=None,
            module=None
        )


class Cache:

    # In‑memory representation: [source (str|None), module (ModuleType|None)]
    _cache: dict[CacheKey, CacheEntry]

    def __init__(
        self,
        fs_location: Path | str | None = None
    ):
        self.fs_location = (
            Path(fs_location).resolve() if fs_location else DEFAULT_CACHE_PATH
        )
        self.fs_location.mkdir(parents=True, exist_ok=True)
        logger.info(f'Using cache directory {self.fs_location}')

        self._cache = {}
        self._warm_from_disk()

    def _warm_from_disk(self) -> None:
        '''
        Populate the in‑memory map with artifacts already on disk.

        '''
        for mod_dir in self.fs_location.iterdir():
            if not mod_dir.is_dir():
                continue

            mod_name = mod_dir.name
            for src_hash_dir in mod_dir.iterdir():
                if not src_hash_dir.is_dir():
                    continue

                key: CacheKey = (mod_name, src_hash_dir.name)
                source: str | None = None
                shared_lib: PyDLL | None = None
                module: ModuleType | None = None

                # load C source if present
                src_path = src_hash_dir / f'{mod_name}.c'
                if src_path.is_file():
                    source = src_path.read_text()
                    logger.debug(f'Loaded source for {mod_name} (hash {key[1]})')

                # load compiled module if present
                mod_path = src_hash_dir / f'{mod_name}{EXT_SUFFIX}'
                if mod_path.is_file():
                    try:
                        shared_lib, module = import_module(mod_name, mod_path)
                        logger.debug(f'Loaded compiled module for {mod_name} (hash {key[1]}')
                    except Exception:  # pragma: no cover – ignore broken cache entries
                        logger.exception(f'Failed to import cached module {mod_path}')

                self._cache[key] = CacheEntry(
                    source=source,
                    shared_lib=shared_lib,
                    module=module
                )

    def get_module_path(self, key: CacheKey) -> Path:
        '''
        Return the directory where *key*'s artifacts are stored.

        '''
        return self.fs_location / key[0] / key[1]

    def get_abi_source(self, key: CacheKey) -> str | None:
        '''
        Return cached C source for *key* or *None* if missing.

        '''
        if key in self._cache and self._cache[key].source:
            logger.debug('Returning in‑memory source for %s', key)
            return self._cache[key].source

        mod_name, _ = key
        src_path = self.get_module_path(key) / f'{mod_name}.c'
        if src_path.is_file():
            logger.debug(f'Reading source for {key} from {src_path}', key, src_path)
            source = src_path.read_text()
            self._cache.setdefault(key, CacheEntry.default()).source = source
            return source

        logger.debug(f'Source for {key} not found')
        return None

    def set_abi_source(self, key: CacheKey, source: str) -> None:
        '''
        Write *source* to disk and cache it in‑memory.

        '''
        logger.debug(f'Storing source for {key}')
        self._cache.setdefault(key, CacheEntry.default()).source = source

        src_dir = self.get_module_path(key)
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / f'{key[0]}.c').write_text(source)

    def get_module(self, key: CacheKey, *, reload: bool = False) -> ModuleType | None:
        '''
        Return compiled module for *key* or *None* if not available.

        '''
        if not reload:
            if key in self._cache and self._cache[key].module:
                logger.debug(f'Returning in‑memory module for {key}')
                return self._cache[key].module

        mod_name, _ = key
        mod_path = self.get_module_path(key) / f'{mod_name}{EXT_SUFFIX}'
        if not mod_path.is_file():
            logger.warning(f'Compiled module not found on disk for {key}')
            return None

        try:
            if key in self._cache and self._cache[key].module:
                # if this module was previously imported we need to delete all
                # refs to it in order to actually get updated behaivour
                entry = self._cache[key]
                # make local scope owner of shared_lib & module objects
                mod = entry.module
                shared_lib = entry.shared_lib
                entry.module = None
                entry.shared_lib = None
                # ensure cleanup
                del mod
                libdl.dlclose(shared_lib._handle)
                del shared_lib

            shared_lib, module = import_module(mod_name, mod_path)

        except Exception:
            logger.exception(f'Failed to import module {mod_path}')
            return None

        self._cache.setdefault(key, CacheEntry.default()).shared_lib = shared_lib
        self._cache.get(key).module = module
        return module
