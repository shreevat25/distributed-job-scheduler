"""Each process entry point must import cleanly in a fresh interpreter.

The test suite itself imports app.main first (via conftest), which can mask
import-order bugs. Running each import in a subprocess catches them.
"""

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "module",
    ["run_worker", "run_scheduler", "run_reaper", "app.main", "app.models"],
)
def test_entrypoint_imports_cleanly(module):
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
