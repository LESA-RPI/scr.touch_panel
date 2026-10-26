"""Check the shipped recovery UX without contacting room hardware."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_browser_recovery_preserves_unknown_receipts_and_experiment_ownership():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable; frontend checks need its standard library")
    subprocess.run(
        [node, str(Path(__file__).with_name("browser_recovery_checks.cjs"))],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
