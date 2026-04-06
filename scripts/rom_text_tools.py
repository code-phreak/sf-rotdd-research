#!/usr/bin/env python3
"""
Thin wrapper for the package-backed ROTDD tooling.

Keeping this script means existing command lines still work, while the actual
logic now lives in `src/rotdd_tools/` where it can grow into a reusable API.
"""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from rotdd_tools.cli import run


if __name__ == "__main__":
    raise SystemExit(run())
