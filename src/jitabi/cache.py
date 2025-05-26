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

import json
import logging
import sysconfig
import importlib

from types import ModuleType
from pathlib import Path
from dataclasses import dataclass


logger = logging.getLogger(__name__)


DEFAULT_CACHE_PATH = Path.home() / '.jitabi'


# `EXT_SUFFIX` is the platform‑specific extension for C extension modules
# (e.g. `.so` on Linux, `.pyd` on Windows).
EXT_SUFFIX = sysconfig.get_config_var('EXT_SUFFIX')


def import_module(
    mod_name: str,
    mod_path: Path,
) -> ModuleType:
    logger.debug(f'Importing module {mod_name} from {mod_path}')

    spec = importlib.util.spec_from_file_location(
        mod_name,
        str(mod_path),
        loader=importlib.machinery.ExtensionFileLoader(mod_name, str(mod_path))
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


default_param_debug: bool = False
default_param_inlined: bool = False
default_param_with_pack: bool = True
default_param_with_unpack: bool = True


@dataclass(frozen=True)
class ModuleParams:
    debug: bool
    inlined: bool
    with_pack: bool
    with_unpack: bool

    def as_dict(self) -> dict:
        return {
            'debug': self.debug,
            'inlined': self.inlined,
            'with_pack': self.with_pack,
            'with_unpack': self.with_unpack
        }

    def as_bytes(self) -> bytes:
        return bytes([
            int(self.debug),
            int(self.inlined),
            int(self.with_pack),
            int(self.with_unpack)
        ])

    @staticmethod
    def from_dict(d: dict) -> ModuleParams:
        return ModuleParams(
            debug=d.get('debug', default_param_debug),
            inlined=d.get('inlined', default_param_inlined),
            with_pack=d.get('with_pack', default_param_with_pack),
            with_unpack=d.get('with_unpack', default_param_with_unpack),
        )

    @staticmethod
    def default() -> ModuleParams:
        return ModuleParams(
            debug=default_param_debug,
            inlined=default_param_inlined,
            with_pack=default_param_with_pack,
            with_unpack=default_param_with_unpack
        )


@dataclass(frozen=True)
class CacheKey:
    mod_name: str
    src_hash: str
    params: ModuleParams

    def __str__(self) -> str:
        s = f'{self.mod_name} (hash {self.src_hash}'

        if (
            self.params.debug or
            self.params.inlined or
            self.params.with_pack or
            self.params.with_unpack
        ):
            s += ', with flags:'

            if self.params.debug:
                s += ' debug'

            if self.params.inlined:
                s += ' inlined'

            if self.params.with_pack:
                s += ' with_pack'

            if self.params.with_unpack:
                s += ' with_unpack'

        s += ')'

        return s


@dataclass
class CacheEntry:
    source: str
    module: ModuleType | None

    @staticmethod
    def from_source(source: str) -> CacheEntry:
        return CacheEntry(
            source=source,
            module=None
        )


class Cache:
    _cache: dict[CacheKey, CacheEntry]

    def __init__(
        self,
        fs_location: Path | str | None = None
    ):
        self.fs_location = (
            Path(fs_location) if fs_location else DEFAULT_CACHE_PATH
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

                src_hash = src_hash_dir.name

                # load params
                params_path = src_hash_dir / 'params.json'
                if not params_path.is_file():
                    logger.warning(
                        f'Could not load params file for {mod_name} (hash {src_hash}),'
                        ' skipping module cache...'
                    )
                    continue

                params = json.loads(params_path.read_text())

                if (
                    'debug' not in params
                    or
                    'inlined' not in params
                    or
                    'with_pack' not in params
                    or
                    'with_unpack' not in params
                ):
                    logger.warning(
                        f'Malformed params file for {mod_name} (hash {src_hash}), '
                        ' skipping module cache...'
                    )
                    continue

                key: CacheKey = CacheKey(
                    mod_name=mod_name,
                    src_hash=src_hash,
                    params=ModuleParams(**params)
                )
                module: ModuleType | None = None

                # load C source if present
                src_path = src_hash_dir / f'{mod_name}.c'
                if src_path.is_file():
                    source = src_path.read_text()
                    logger.debug(
                        f'Loaded source for {str(key)})'
                    )

                else:
                    logger.warning(
                        f'Source not found for {key}, skipping load...'
                    )
                    continue

                # load compiled module if present
                mod_path = src_hash_dir / f'{mod_name}{EXT_SUFFIX}'
                if mod_path.is_file():
                    try:
                        module = import_module(mod_name, mod_path)
                        logger.debug(
                            f'Loaded compiled module for {str(key)})'
                        )

                    except Exception:
                        logger.exception(
                            f'Failed to import cached module {str(key)})'
                        )
                        continue

                self._cache[key] = CacheEntry(
                    source=source,
                    module=module
                )

    def get_module_path(self, key: CacheKey) -> Path:
        '''
        Return the directory where *key*'s artifacts are stored.

        '''
        return self.fs_location / key.mod_name / key.src_hash

    def get_abi_source(
        self,
        key: CacheKey,
        force_reload: bool = False
    ) -> str | None:
        '''
        Return cached source for *key* or *None* if missing.

        '''
        if not force_reload and key in self._cache:
            logger.debug(f'Returning in‑memory source for {key}')
            return self._cache[key].source

        module_path = self.get_module_path(key)

        src_path = module_path / f'{key.mod_name}.c'
        if src_path.is_file():
            logger.debug(f'Reading C source for {key} from {src_path}')
            source = src_path.read_text()
            self._cache.setdefault(key, CacheEntry.from_source(source)).source = source

            return source

        return None

    def set_abi_source(
        self,
        key: CacheKey,
        source: str,
    ) -> None:
        '''
        Write *source* to disk and cache it in‑memory.

        '''
        logger.debug(f'Storing sources for {key}')
        self._cache.setdefault(key, CacheEntry.from_source(source)).source = source

        src_dir = self.get_module_path(key)
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / f'{key.mod_name}.c').write_text(source)

    def get_module(
        self,
        key: CacheKey,
        *,
        force_reload: bool = False
    ) -> ModuleType | None:
        '''
        Return compiled module for *key* or *None* if not available.

        '''
        entry = self._cache.get(key, None)
        if not entry:
            return None

        if not force_reload:
            if entry.module:
                logger.debug(f'Returning in‑memory module for {key}')
                return entry.module

        mod_path = self.get_module_path(key) / f'{key.mod_name}{EXT_SUFFIX}'
        if not mod_path.is_file():
            logger.warning(f'Compiled module not found on disk for {key}')
            return None

        try:
            module = import_module(key.mod_name, mod_path)

        except Exception:
            logger.exception(f'Failed to import module {mod_path}')
            return None

        self._cache.setdefault(key, CacheEntry.from_source(entry.source)).module = module
        return module
