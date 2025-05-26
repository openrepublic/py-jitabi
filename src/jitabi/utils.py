from __future__ import annotations

import os
import re
import json
import sysconfig
import subprocess

from shutil import which


_RAW_TYPE_RE = re.compile(r'^raw\(\d+\)$')

def is_raw_type(name: str) -> bool:
    return name == 'raw' or _RAW_TYPE_RE.match(name)


def normalize_dict(d: dict) -> dict:
    return json.loads(
        json.dumps(d, sort_keys=True, cls=JSONHexEncoder)
    )


class JSONHexEncoder(json.JSONEncoder):
    def default(self, obj):
        # hex string on bytes
        if isinstance(obj, (bytes, bytearray)):
            return f'bytes({obj.hex()})'

        if isinstance(obj, type):
            return str(obj)

        try:
            return super().default(obj)

        except Exception as e:
            return f'Unknown!: {e}'


def detect_working_compiler() -> str | None:
    '''
    Find if any of the supported compilers is on PATH
    Returns ``None`` if nothing usable is found.

    '''
    # candidate list:  $CC -> sysconfig -> common names
    candidates: list[str] = []

    env_cc = os.environ.get('CC')
    if env_cc:
        candidates.extend(env_cc.split()[0])  # env var may contain flags

    cc_from_cfg = sysconfig.get_config_var('CC')
    if cc_from_cfg:
        candidates.append(cc_from_cfg.split()[0])

    # fall-back guesses
    candidates.extend(['cc', 'gcc', 'clang', 'cl'])

    seen: set[str] = set()
    for cmd in candidates:
        cmd = cmd.strip()
        if not cmd or cmd in seen:
            continue
        seen.add(cmd)

        # Is the binary on PATH?
        exe = which(cmd)
        if exe:
            return exe

    return None


def detect_compiler_type(cmd: str) -> str | None:
    '''
    Runs `cmd --version` (or `cmd -v`) and heuristically looks for
    'clang' or 'gcc' in the output.

    '''
    for args in ([cmd], [cmd, '--version'], [cmd, '-v']):
        try:
            out = subprocess.check_output(args, stderr=subprocess.STDOUT, text=True)
        except subprocess.CalledProcessError as e:
            out = e.output

        except FileNotFoundError:
            continue

        lower = out.lower()
        if 'clang' in lower:
            return 'clang'
        if 'gcc' in lower or 'free software foundation' in lower:
            return 'gcc'
        if 'microsoft' in lower:
            return 'cl'
    return None
