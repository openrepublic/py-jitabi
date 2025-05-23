# py-jitabi

> **Just-In-Time ABI → C extensions for Python**

**py-jitabi** turns an [Antelope](https://github.com/AntelopeIO) (formerly EOSIO) ABI description into a blazing-fast CPython extension module that provides **pack / unpack** helpers for every struct, enum and alias.

---

## Highlights

| | |
|---|---|
| **Native speed** | ABI definitions are rendered into C with [Jinja 2] templates and compiled on-the-fly with your system compiler (GCC or Clang). |
| **Pluggable front-end** | Ship your own `ABIView` implementation – JSON, YAML, SQL, anything – and jitabi will happily consume it. |
| **Smart on-disk cache** | Generated C source and shared objects are kept under `~/.jitabi/` (or a path you choose) so subsequent runs are instant. |
| **Pure-Python API** | No extra build steps – import, call, profit. |

---

## Requirements

* **Python ≥ 3.10**
* **C99-compatible compiler**: GCC ≥ 9, Clang ≥ 10, MSVC ≥ 19.28 (VS 2019+)

---

## Installation

Clone the repository and install in editable mode:

```bash
git clone https://github.com/yourname/py-jitabi.git
cd py-jitabi
pip install -e .
```

---

## Quick start

```python
from jitabi import JITContext
from jitabi.json import ABI

# Load an ABI – any object implementing jitabi.protocol.ABIView works
abi = ABI.from_file("std_abi.json")

# Ask the JIT for a module (cached under ~/.jitabi)
jit = JITContext()
std = jit.module_for_abi("standard", abi, debug=False, with_pack=True)

raw   = bytes.fromhex("01170000…")            # binary from the wire
value = std.unpack_result(raw)                # dict → Python types
raw2  = std.pack_result(value)                # round-trip back to bytes
assert raw == raw2
```

### Controlling the cache location

```python
jit = JITContext(cache_path="./.jitabi")
```

### Enabling debug logging

```python
std = jit.module_for_abi("standard", abi, debug=True)
```

Generated C files contain calls such as `logger.debug("struct block_position unpacked: …")` which are routed to `logging.getLogger("jitabi.standard")`.

---

## Project layout (TL;DR)

```
jitabi/
├── codegen.py   # Jinja2 → C generator & compiler wrapper
├── cache.py     # Filesystem + in-memory cache
├── __init__.py  # JITContext orchestrator
├── protocol.py  # ABIView protocol + utilities
├── json.py      # Reference ABIView for JSON ABIs
└── templates/   # .c.j2 code templates used by the generator
```

---

## Testing

The test-suite uses [pytest] + [DeepDiff].  Create an isolated env with [uv] and run:

```bash
uv venv .venv --python=3.10
uv sync            # installs dev-deps
uv run pytest -s --log-cli-level=debug
```

Continuous-integration workflows for Ubuntu and macOS live in `.github/workflows/`.

---

## License

**GNU AGPL v3 or later** – see `LICENSE` for details.

---
