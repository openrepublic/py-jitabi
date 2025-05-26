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
Code generation and compilation routines for ABI C modules.

'''
import sys as py_sys
import time
import json
import logging

from pathlib import Path
from setuptools._distutils import (
    ccompiler,
    sysconfig
)

from jitabi.cache import ModuleParams
from jitabi.utils import detect_compiler_type


logger = logging.getLogger(__name__)


def _compile_with_distutils(
    name: str,
    src: Path,
    build: Path,
    defines: list[str] = [],
):
    '''
    Compile *src* into <build_dir>/<name><EXT_SUFFIX> with the supported
    compilers:

        on unix:
            - gcc
            - clang

        on windows:
            - cl
            - clang
    '''
    cc = ccompiler.new_compiler()
    sysconfig.customize_compiler(cc)

    # strip out any -DNDEBUG that came in via Python’s CFLAGS
    for attr in ('compiler', 'compiler_so'):
        flags = getattr(cc, attr, None)
        if isinstance(flags, list):
            setattr(cc, attr, [f for f in flags if f != '-DNDEBUG'])

    is_unix: bool = cc.compiler_type == 'unix'

    include_py = sysconfig.get_config_var('INCLUDEPY')

    # extra_postargs for cc.compile call
    extra: list[str] = (
        [
            '-std=c99',
            '-pedantic',
            '-Wno-unused-function'
        ]
        if is_unix
        else []
    )

    specific_type = detect_compiler_type(
        Path(cc.compiler[0]).name
        if is_unix
        else 'cl.exe'
    )

    if specific_type == 'gcc':
        extra += ['-Wno-maybe-uninitialized']

    elif specific_type == 'clang':
        extra += ['-Wno-sometimes-uninitialized']

    elif specific_type == 'cl':
        # equivalent of -Wno-maybe-uninitialized
        extra = ['/wd4701']

    libs: list[str]  = []
    library_dirs: list[str]  = []

    if cc.compiler_type == 'msvc':
        # need to add -lpythonVERSION lib implicitly
        ver = sysconfig.get_config_var('VERSION')
        libname = f'python{ver.replace(".", "")}'

        # maybe debug build of CPython?
        if hasattr(py_sys, 'gettotalrefcount'):
            libname += '_d'

        libs.append(libname)

        libdir = (
            sysconfig.get_config_var('LIBDIR') or  # venvs
            sysconfig.get_config_var('LIBPL')  or  # embedded/dist
            Path(py_sys.base_prefix) / 'libs'
        )
        library_dirs.append(str(libdir))

        if specific_type == 'clang':
            extra += [
                '-Wno-visibility'
            ]

    for define in defines:
        cc.define_macro(define)

    logger.info(f'Compiling {src}...')
    start_compile = time.time()
    objs = cc.compile(
        [str(src)],
        include_dirs=[include_py],
        extra_postargs=extra
    )
    compile_elapsed = time.time() - start_compile
    logger.info(f'Done compiling, took: {compile_elapsed:.2f}s')

    start_link = time.time()
    ext = sysconfig.get_config_var('EXT_SUFFIX')
    target = build / f'{name}{ext}'
    cc.link_shared_object(
        objs,
        str(target),
        libraries=libs,
        library_dirs=library_dirs,
    )
    link_elapsed = time.time() - start_link
    logger.info(f'Done linking, took: {link_elapsed:.2f}s')
    logger.info(f'Total time: {compile_elapsed + link_elapsed:.2f}s')
    return target



def compile_module(
    name: str,
    source: str,
    build_path: Path | str,
    build_params: ModuleParams,
):
    '''
    Compile the generated C source into a shared object for import.

    '''
    # ensure build dir exists
    build_path = Path(build_path)
    build_path.mkdir(parents=True, exist_ok=True)

    # write the C code to a file
    c_path = build_path / f'{name}.c'
    c_path.write_text(source)

    defs = []
    if build_params.debug:
        defs.append('__JITABI_DEBUG')

    if build_params.inlined:
        defs.append('__JITABI_INLINED')

    if build_params.with_unpack:
        defs.append('__JITABI_UNPACK')

    if build_params.with_pack:
        defs.append('__JITABI_PACK')

    _compile_with_distutils(name, c_path, build_path, defines=defs)

    # write build params to json file on build dir
    (build_path / 'params.json').write_text(
        json.dumps(build_params.as_dict(), indent=4)
    )
