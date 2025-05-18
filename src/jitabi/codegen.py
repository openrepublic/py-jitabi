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
import json
import logging
import subprocess

from pathlib import Path
from setuptools._distutils import (
    ccompiler,
    sysconfig
)

from jinja2 import Environment, FileSystemLoader

from jitabi.json import ABIStruct
from jitabi.sanitize import (
    check_type,
    check_ident
)
from jitabi.protocol import (
    STD_TYPES,
    DEFAULT_STRUCTS,
    DEFAULT_ALIASES,
    TypeModifier,
    ABIView,
)


logger = logging.getLogger(__name__)


TEMPLATE_DIR = Path(__file__).with_name('templates')
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=False,
)
module_tmpl = env.get_template('module.c.j2')

unpack_alias_tmpl = env.get_template('unpack_alias.c.j2')
pack_alias_tmpl = env.get_template('pack_alias.c.j2')

unpack_enum_tmpl = env.get_template('unpack_enum.c.j2')
pack_enum_tpl = env.get_template('pack_enum.c.j2')

unpack_struct_tmpl = env.get_template('unpack_struct.c.j2')
pack_struct_tmpl = env.get_template('pack_struct.c.j2')


def fn_meta_from(
    type_name: str,
    valid_types: list[str]
) -> dict:
    '''
    Given an antelope type name like `uint32[]` or `test_struct?` create a
    function meta dict with the keys:

        - type_name: actual type name without any modifiers
        - modifier: a TypeModifier enum value
        - args: extra arguments needed to call function (only used for
            raw(len))

    `valid_types` argument is a string list of:
        - all std types + `'raw'`
        - all struct names
        - all enum names
        - all aliases

    '''
    og_name = type_name  # store original name before any manipulation

    args: list[str] = []
    if type_name.startswith('raw(') and type_name.endswith(')'):
        # if type_name is a raw with a len param
        raw_len = type_name.split('(')[1].split(')')[0]
        # append extracted len to args
        args.append(raw_len)
        # chop off len argument
        type_name = 'raw'

    # check that type_name is a valid antelope type (prevents injections)
    check_type(type_name)

    # in case type_name has a modifier, chop it off and set correct
    # TypeModifier value
    modifier = TypeModifier.NONE
    if type_name.endswith('[]'):
        type_name = type_name[:-2]
        modifier = TypeModifier.ARRAY

    elif type_name.endswith('?'):
        type_name = type_name[:-1]
        modifier = TypeModifier.OPTIONAL

    elif type_name.endswith('$'):
        type_name = type_name[:-1]
        modifier = TypeModifier.EXTENSION

    # finally after ensuring type_name is a bare type with no modifiers
    # check if its in the list of valid types or raise
    if type_name not in valid_types:
        raise TypeError(f'{og_name} not a valid type!:\n{valid_types}')

    return {
        'type_name': type_name,
        'modifier': modifier,
        'args': args
    }


def c_source_from_abi(
    name: str,
    abi_hash: str,
    abi: ABIView
) -> str:
    '''
    Given a module name and an object implementing the ABIView protocol,
    generate a C source file that defines serialization routines for the types
    defined by the ABIView, return it as a string.

    '''
    # check module name is valid (prevents injections)
    check_ident(name, what='module name')

    # generate list of valid type names
    valid_types = [
        'raw',
        *STD_TYPES,
        *[ntype for ntype in DEFAULT_ALIASES],
        *[s['name'] for s in DEFAULT_STRUCTS],
        *[s.name() for s in abi.structs()],
        *[e.name() for e in abi.enums()],
        *[a.new_type_name() for a in abi.aliases()]
    ]

    functions: list[dict] = []

    struct_defs = [
        ABIStruct(struct_def=sdef)
        for sdef in DEFAULT_STRUCTS
    ] + abi.structs()
    for struct_meta in struct_defs:
        sname = struct_meta.name()
        check_ident(sname, f'struct {sname}')

        bname = struct_meta.base()
        if bname:
            check_ident(bname, f'struct base {bname}')

        fields = []
        for f in struct_meta.fields():
            fname = f.name()
            check_ident(fname, f'struct {sname} field {fname}')
            fields.append({
                'name': fname,
                'call': fn_meta_from(f.type_name(), valid_types)
            })

        functions.append({
            'name': sname,
            'unpack_code': unpack_struct_tmpl.render(
                fn_name=sname,
                base=bname,
                fields=fields
            ),
            'pack_code': pack_struct_tmpl.render(
                fn_name=sname,
                base=bname,
                fields=fields
            )
        })

    for enum_meta in abi.enums():
        ename = enum_meta.name()
        check_ident(ename, f'enum {ename}')

        variants = []
        for variant in enum_meta.variants():
            check_ident(variant, f'enum variant {variant}')
            variants.append({
                'name': variant,
                'is_std': variant in STD_TYPES
            })

        functions.append({
            'name': ename,
            'unpack_code': unpack_enum_tmpl.render(
                enum_name=ename,
                variants=variants
            ),
            'pack_code': pack_enum_tpl.render(
                enum_name=ename,
                variants=variants
            )
        })

    alias_defs = DEFAULT_ALIASES
    for a in abi.aliases():
        anew = a.new_type_name()
        check_ident(anew, f'alias {anew}')
        afrom = a.from_type_name()
        check_ident(afrom, f'alias {anew} from {afrom}')

        if anew in alias_defs:
            old_target = alias_defs.get(anew, None)
            if old_target and old_target != afrom:
                logger.warning(
                    f'Replaced alias def {anew}, was {old_target} now is {afrom}'
                )

        alias_defs[anew] = afrom

    aliases = [
        {
            'alias': new_type_name,
            'unpack_code': unpack_alias_tmpl.render(
                alias=new_type_name,
                call=fn_meta_from(from_type_name, valid_types)
            ),
            'pack_code': pack_alias_tmpl.render(
                alias=new_type_name,
                call=fn_meta_from(from_type_name, valid_types)
            )
        }
        for new_type_name, from_type_name in alias_defs.items()
    ]

    logger.debug(f'Function names: {json.dumps([f["name"] for f in functions], indent=4)}')
    logger.debug(f'Aliases: {json.dumps(alias_defs, indent=4)}')

    source = module_tmpl.render(
        m_name=name,
        m_doc=name,
        aliases=aliases,
        functions=functions
    )

    return source


def detect_unix_compiler_type(cmd: str) -> str | None:
    '''
    Runs `cmd --version` (or `cmd -v`) and heuristically looks for
    'clang' or 'gcc' in the output.

    '''
    for args in ([cmd, '--version'], [cmd, '-v']):
        try:
            out = subprocess.check_output(args, stderr=subprocess.STDOUT, text=True)
        except subprocess.CalledProcessError as e:
            out = e.output
        lower = out.lower()
        if 'clang' in lower:
            return 'clang'
        if 'gcc' in lower or 'free software foundation' in lower:
            return 'gcc'
    return None


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
    '''
    cc = ccompiler.new_compiler()
    sysconfig.customize_compiler(cc)

    include_py = sysconfig.get_config_var('INCLUDEPY')

    libs: list[str]  = []
    library_dirs: list[str]  = []
    extra: list[str] = []

    # translate to the right flag dialect
    if cc.compiler_type == 'unix':
        specific_type = detect_unix_compiler_type(Path(cc.compiler[0]).name)

        if specific_type == 'gcc':
            extra = ['-Wno-maybe-uninitialized']

        elif specific_type == 'clang':
            extra = ['-Wno-sometimes-uninitialized']

    else:
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

        # equivalent of -Wno-maybe-uninitialized
        extra = ['/wd4701']

    for define in defines:
        cc.define_macro(define)

    objs = cc.compile(
        [str(src)],
        include_dirs=[include_py],
        extra_postargs=extra
    )

    ext = sysconfig.get_config_var('EXT_SUFFIX')
    target = build / f'{name}{ext}'
    cc.link_shared_object(
        objs,
        str(target),
        libraries=libs,
        library_dirs=library_dirs,
    )
    return target



def compile_module(
    name: str,
    source: str,
    build_path: Path | str,
    debug: bool = False,
    with_unpack: bool = True,
    with_pack: bool = True
):
    '''
    Compile the generated C source into a shared object for import.

    '''
    # ensure build dir exists
    build_path = Path(build_path).resolve()
    build_path.mkdir(parents=True, exist_ok=True)

    # write the C code to a file
    c_path = build_path / f'{name}.c'
    c_path.write_text(source)

    defs = []
    if debug:
        defs.append('__JITABI_DEBUG')

    if with_unpack:
        defs.append('__JITABI_UNPACK')

    if with_pack:
        defs.append('__JITABI_PACK')

    _compile_with_distutils(name, c_path, build_path, defines=defs)
