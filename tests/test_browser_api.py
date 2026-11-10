"""Run the shipped API module's receipt behaviour with Node's standard library."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_browser_api():
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("Node.js is required for browser API checks in CI")
        pytest.skip("Node.js unavailable")
    subprocess.run(
        [node, "--test", str(Path(__file__).with_name("browser_api.test.mjs"))],
        check=True, capture_output=True, text=True, timeout=10,
    )
