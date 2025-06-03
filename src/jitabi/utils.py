from __future__ import annotations

import os
import sysconfig
import subprocess

from shutil import which


if os.name == "nt":
    # Win32
    import msvcrt

    def fd_lock(fd, exclusive: bool):
        mode = msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK
        msvcrt.locking(fd, mode, 1)

    def fd_unlock(fd):
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    # POSIX
    import fcntl

    def fd_lock(fd, exclusive: bool):
        flag = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(fd, flag)

    def fd_unlock(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)


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
