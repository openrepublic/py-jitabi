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

from types import ModuleType
from pathlib import Path

import jitabi.codegen as codegen

from jitabi.cache import Cache
from jitabi.protocol import (
    ABIView,
    hash_abi_view
)

from jitabi.utils import detect_working_compiler


if not detect_working_compiler():
    raise RuntimeError('A C compiler is required please set the CC flag')


logger = logging.getLogger(__name__)


class JITContext:
    '''
    Encapsulates caching + codegen + compilation.

    '''

    def __init__(
        self,
        cache_path: Path | str | None = None
    ):
        self._cache = Cache(fs_location=cache_path)
        logger.info(
            f'Initialized JITContext with cache at {self._cache.fs_location}'
        )

        self._versions: dict = {}

    def _full_mod_name(self, name: str) -> str:
        return f'{name}_{self._versions.setdefault(name, 0)}'

    def _inc_mod_name(self, name: str):
        self._versions[name] += 1

    def c_source_from_abi(
        self,
        name: str,
        abi: ABIView,
        *,
        use_cache: bool = True
    ) -> tuple[str, str]:
        '''
        Return ``(abi_hash, c_source)`` for *abi*, reusing cached source if
        available.

        '''
        name = self._full_mod_name(name)

        abi_hash = hash_abi_view(abi)
        if use_cache:
            logger.debug(f'Looking up C source for {name} (hash {abi_hash})')

            source = self._cache.get_abi_source((name, abi_hash))
            if source is not None:
                logger.debug(f'Found cached C source for {name} (hash {abi_hash})')
                return abi_hash, source

        logger.debug(f'Generating new C source for {name} (hash {abi_hash})')
        key = (name, abi_hash)
        # nonce = self._cache.get_entry_nonce(key)
        source = codegen.c_source_from_abi(name, abi_hash, abi)
        self._cache.set_abi_source(key, source)
        return abi_hash, source

    def compile_module(
        self,
        mod_name: str,
        src_hash: str,
        source: str,
        *,
        debug: bool = False,
        with_unpack: bool = True,
        with_pack: bool = True,
        use_cache: bool = True
    ) -> ModuleType:
        '''
        Ensure compiled extension for *(mod_name, src_hash)* exists and return
        it.

        '''
        mod_name = self._full_mod_name(mod_name)

        logger.debug(
            f'Requesting compiled module for {mod_name} (hash {src_hash})'
        )
        if use_cache:
            module = self._cache.get_module((mod_name, src_hash))
            if module is not None:
                logger.debug(
                    f'Using cached compiled module for {mod_name} (hash {src_hash})'
                )
                return module

        # not cached: compile now
        logger.info(f'Compiling module {mod_name} (hash {src_hash})')
        output_dir = self._cache.get_module_path((mod_name, src_hash))
        codegen.compile_module(
            mod_name,
            source,
            output_dir,
            debug=debug,
            with_unpack=with_unpack,
            with_pack=with_pack
        )

        module = self._cache.get_module((mod_name, src_hash), reload=True)
        if module is None:
            raise RuntimeError(
                'Compilation succeeded but '
                f'module could not be imported: {mod_name}'
            )

        return module

    def module_for_abi(
        self,
        mod_name: str,
        abi: ABIView,
        *,
        debug: bool = False,
        with_unpack: bool = True,
        with_pack: bool = True,
        use_cache: bool = True
    ) -> ModuleType:
        '''
        Return a compiled extension for *abi*, compiling it if necessary.

        '''
        full_mod_name = self._full_mod_name(mod_name)
        src_hash = hash_abi_view(abi)
        logger.debug(f'Requesting module for {full_mod_name} (hash {src_hash})')

        module = self._cache.get_module((full_mod_name, src_hash))
        if use_cache:
            if module is not None:
                logger.debug(
                    f'Using cached module for {full_mod_name} (hash {src_hash})'
                )
                return module

        elif module:
            self._inc_mod_name(mod_name)

        _, source = self.c_source_from_abi(
            mod_name,
            abi,
            use_cache=use_cache
        )

        return self.compile_module(
            mod_name,
            src_hash,
            source,
            debug=debug,
            with_unpack=with_unpack,
            with_pack=with_pack,
            use_cache=use_cache
        )
