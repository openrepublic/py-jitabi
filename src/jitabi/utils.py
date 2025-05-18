import os
import json
import sysconfig
import subprocess
from shutil import which


class JSONHexEncoder(json.JSONEncoder):
    def default(self, obj):
        # hex string on bytes
        if isinstance(obj, (bytes, bytearray)):
            return obj.hex()

        return super().default(obj)


def detect_working_compiler() -> str | None:
    '''
    Return the *command* of a C compiler that both exists in PATH **and**
    answers to “--version”.  
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
        if not exe:
            continue

        # Does it appear to work?
        try:
            subprocess.run([exe, '--version'],
                           capture_output=True, check=False, timeout=3)
            return exe          # good enough
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            pass

    return None
