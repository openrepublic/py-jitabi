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
High‑level façade around :pymod:`jitabi.codegen` that handles on‑disk caching,
C source generation, and JIT compilation of ABI‑specific Python extension
modules.

Typical usage::

    ctx = JITContext()
    mod = ctx.module_for_abi('my_abi', abi_view)
    result = mod.unpack_mystruct(buf)

All heavy lifting (C source generation & compilation) happens only on the
first call for a given *(module_name, abi_hash)* pair; subsequent calls reuse
artifacts stored in ``~/.jitabi`` (or the path you pass as *cache_path*).

'''
import logging
import hashlib

from types import ModuleType
from pathlib import Path

import jitabi.codegen as codegen

from jitabi.cache import (
    ModuleParams,
    CacheKey,
    Cache
)
from jitabi.compiler import compile_module
from jitabi.protocol import ABIDef, ABIView

from jitabi.utils import detect_working_compiler


logger = logging.getLogger(__name__)


def hash_abi_for_cache(
    abi: ABIView,
    params: ModuleParams,
    *,
    as_bytes: bool = False
) -> str | bytes:
    abi_hash = abi.hash(as_bytes=True)

    h = hashlib.sha256()
    h.update(codegen.hash_pipeline(as_bytes=True))
    h.update(abi_hash)
    h.update(params.as_bytes())

    return (
        h.digest() if as_bytes
        else h.hexdigest()
    )


class JITContext:
    '''
    Encapsulates caching + codegen + compilation.

    '''

    def __init__(
        self,
        cache_path: Path | str | None = None,
        readonly: bool = False,  # dont allow source regeneration or compilation
        ipc_locked: bool = True  # use ipc locks when accesing cache directories
    ):
        if not readonly and not detect_working_compiler():
            raise RuntimeError(
                'A C compiler is required to initialize a JITContext with '
                'readonly=False, please set the CC flag or open JITContext '
                'in readonly mode.'
            )

        self._cache = Cache(fs_location=cache_path, ipc_locked=ipc_locked)
        self._readonly = readonly
        logger.info(
            f'Initialized JITContext with cache at {self._cache.fs_location}'
        )

        self._versions: dict = {}

    def _full_mod_name(self, name: str) -> str:
        name = name.replace('.', '_')
        return f'{name}_{self._versions.setdefault(name, 0)}'

    def _inc_mod_name(self, name: str):
        name = name.replace('.', '_')
        self._versions[name] += 1

    def _source_from_abi(
        self,
        key: CacheKey,
        abi: ABIView,
        abi_location: Path,
        *,
        force_reload: bool = False,
    ) -> str:
        '''
        Return ``(c_source, pytest_source)`` for *abi*, reusing cached source if available.

        '''
        if not force_reload:
            logger.debug(f'Looking up sources for {key})')

            source = self._cache.get_abi_source(key, force_reload=force_reload)
            if source is not None:
                logger.debug(f'Found cached C source for {key})')
                return source

        if self.is_readonly:
            raise RuntimeError('Source not found and in read only context!')

        logger.debug(f'Generating new C source for {key})')
        source = codegen.c_source_from_abi(
            key.mod_name,
            key.src_hash,
            abi
        )

        self._cache.set_abi_source(key, source)
        return source

    def _compile_module(
        self,
        key: CacheKey,
        source: str,
        *,
        force_reload: bool = False,
    ) -> ModuleType:
        '''
        Ensure compiled extension for *(mod_name, src_hash)* exists and return
        it.

        '''
        logger.debug(
            f'Requesting compiled module for {key})'
        )
        module = self._cache.get_module(key, force_reload=force_reload)
        if not force_reload:
            if module is not None:
                logger.debug(
                    f'Using cached compiled module for {key})'
                )
                return module

        if self.is_readonly:
            raise RuntimeError('Module not found and in read only context!')

        # not cached: compile now
        logger.info(f'Compiling module {key})')
        output_dir = self._cache.get_module_path(key)
        with self._cache.dir_lock(output_dir, shared=False):
            compile_module(
                key.mod_name,
                source,
                output_dir,
                key.params
            )

        module = self._cache.get_module(key, force_reload=True)
        if module is None:
            raise RuntimeError(
                'Compilation succeeded but '
                f'module could not be imported: {key}'
            )

        return module

    @property
    def is_readonly(self) -> bool:
        return self._readonly

    def module_dir_for(self, key: CacheKey) -> Path:
        return self._cache.get_module_path(key)

    def module_for_abi(
        self,
        name: str,
        abi: ABIDef | ABIView,
        *,
        force_reload: bool = False,
        params: dict | ModuleParams = {}
    ) -> tuple[CacheKey, ModuleType]:
        '''
        Return a compiled extension for *abi*, compiling it if necessary.

        '''
        params: ModuleParams = ModuleParams.from_dict(params)
        abi = ABIView.from_abi(abi)

        full_name = self._full_mod_name(name)
        src_hash = hash_abi_for_cache(abi, params)
        key = CacheKey(
            mod_name=full_name,
            src_hash=src_hash,
            params=params
        )
        logger.debug(f'Requesting module for {key})')

        module = self._cache.get_module(key, force_reload=force_reload)
        if not force_reload:
            if module is not None:
                logger.debug(
                    f'Using cached module for {key})'
                )
                return key, module

        if self.is_readonly:
            raise RuntimeError('Module not cached and in read only context!')

        # user requested disk reload & module already existed
        # increment mod name to trigger full re-import
        self._inc_mod_name(name)

        # store actual ABIView as file
        mod_dir = self.module_dir_for(key)
        mod_dir.mkdir(parents=True, exist_ok=True)
        abi_location = mod_dir / f'{name}.json'
        abi_location.write_bytes(abi.definition.as_bytes())

        source = self._source_from_abi(
            key, abi, abi_location,
            force_reload=force_reload
        )

        return (
            key,
            self._compile_module(
                key, source,
                force_reload=force_reload,
            )
        )
