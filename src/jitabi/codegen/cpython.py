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
import json
import logging

from jitabi.sanitize import (
    check_type,
    check_ident
)
from jitabi.protocol import (
    is_raw_type,
    is_std_type,
    ABIView,
)
from jitabi.templates import (
    module_tmpl,
    unpack_alias_tmpl,
    pack_alias_tmpl,
    unpack_enum_tmpl,
    pack_enum_tmpl,
    unpack_struct_tmpl,
    pack_struct_tmpl,
)


logger = logging.getLogger(__name__)


def try_c_source_from_abi(
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

    functions: list[dict] = []

    for struct_meta in abi.structs:
        sname = struct_meta.name
        check_ident(sname, f'struct {sname}')

        bname = struct_meta.base
        if bname:
            check_ident(bname, f'struct base {bname}')

        fields = []
        for f in struct_meta.fields:
            fname = f.name
            check_ident(fname, f'struct {sname} field {fname}')
            check_type(f.type_)
            fields.append({
                'name': fname,
                'call': abi.resolve_type(f.type_)
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

    alias_defs = {}
    for a in abi.types:
        anew = a.new_type_name
        afrom = a.type_
        check_ident(anew, f'alias {anew} -> {afrom}')
        check_ident(afrom, f'alias {anew} -> {afrom}', allow_raw=True)

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
                call=abi.resolve_type(from_type_name)
            ),
            'pack_code': pack_alias_tmpl.render(
                alias=new_type_name,
                call=abi.resolve_type(from_type_name)
            )
        }
        for new_type_name, from_type_name in alias_defs.items()
    ]

    for var_meta in abi.variants:
        ename = var_meta.name
        check_ident(ename, f'enum {ename}')

        variants = []
        targets = {}
        for i, variant in enumerate(var_meta.types):
            check_ident(variant, f'enum variant {variant}')
            var_call = abi.resolve_type(variant)
            var_type = var_call.resolved_name

            is_std = is_std_type(var_type)
            is_raw = not is_std and is_raw_type(var_type)

            if is_raw or var_type == 'bytes':
                targets['bytes'] = i

            elif is_std:
                if var_type == 'string':
                    targets['string'] = i

                elif 'int' in var_type:
                    targets['int'] = i

                elif 'float' in var_type:
                    targets['float'] = i

                elif var_type == 'bool':
                    targets['bool'] = i

                else:
                    raise TypeError(f'Unknown std type {var_type}')

            else:
                targets['dict'] = 0  # dummy value

            variants.append({
                'name': variant,
                'call': var_call,
                'is_std': is_std or is_raw
            })

        functions.append({
            'name': ename,
            'unpack_code': unpack_enum_tmpl.render(
                enum_name=ename,
                variants=variants
            ),
            'pack_code': pack_enum_tmpl.render(
                enum_name=ename,
                input_types=list(targets.keys()),
                targets=targets,
                variants=variants
            )
        })

    logger.debug(f'Function names: {json.dumps([f["name"] for f in functions], indent=4)}')
    logger.debug(f'Aliases: {json.dumps(alias_defs, indent=4)}')

    source = module_tmpl.render(
        m_name=name,
        m_doc=name,
        aliases=aliases,
        functions=functions
    )

    return source


def c_source_from_abi(
    name: str,
    abi_hash: str,
    abi: ABIView
) -> str:
    try:
        return try_c_source_from_abi(name, abi_hash, abi)

    except Exception as e:
        logger.error(
            'While generating C source:\n'
            f'\tname: {name}'
            f'\tabi_hash: {abi_hash}'
        )
        raise e
