'''
Utilities for loading C Jinja 2 templates and computing a SHA-256 hash of
their raw UTF-8 sources.

'''
import hashlib

from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined
)


TEMPLATE_DIR = Path(__file__).parent

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    undefined=StrictUndefined,
    autoescape=False
)

# Template objects
module_tmpl = env.get_template('module.c.j2')
unpack_alias_tmpl = env.get_template('unpack_alias.c.j2')
pack_alias_tmpl = env.get_template('pack_alias.c.j2')
unpack_enum_tmpl = env.get_template('unpack_enum.c.j2')
pack_enum_tmpl = env.get_template('pack_enum.c.j2')
unpack_struct_tmpl = env.get_template('unpack_struct.c.j2')
pack_struct_tmpl = env.get_template('pack_struct.c.j2')

_template_names = [
    'macros.c.j2',
    'module.c.j2',
    'pack_alias.c.j2',
    'pack_enum.c.j2',
    'pack_struct.c.j2',
    'unpack_alias.c.j2',
    'unpack_enum.c.j2',
    'unpack_struct.c.j2',
]


def hash_templates(as_bytes: bool = False) -> str | bytes:
    '''
    Compute a deterministic SHA-256 over all template sources

    '''
    hasher = hashlib.sha256()
    for name in sorted(_template_names):
        source, *_ = env.loader.get_source(env, name)
        hasher.update(source.encode('utf-8'))

    return (
        hasher.digest() if as_bytes
        else hasher.hexdigest()
    )
