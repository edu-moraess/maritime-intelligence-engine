"""Targeted P0 validation; deliberately excludes model-training and live-network tests."""

from __future__ import annotations

import compileall
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


P0_TESTS = (
    "tests/test_ingestion_worker.py",
    "tests/test_collection_windows.py",
    "tests/test_aisstream_provider.py",
    "tests/test_sidebar_connection_state.py",
    "tests/test_sidebar_surface.py",
    "tests/test_tactical_map.py",
    "tests/test_traffic_metrics.py",
    "tests/test_region_comparison.py",
    "tests/test_environmental_context.py",
    "tests/test_engine_environmental_context.py",
    "tests/test_ingestion_settings.py",
    "tests/test_process_engine_registry.py",
)


def main() -> int:
    os.chdir(REPO_ROOT)
    base_sha = "5bbe456f657bd4524e71937cf73da420db4f0898"
    print("[P0] Checking patch whitespace and merge markers ...", flush=True)
    import subprocess
    subprocess.run(
        ["git", "diff", "--check", base_sha, "HEAD"],
        cwd=REPO_ROOT,
        check=True,
    )

    print("[P0] Compiling app.py, src/, and tests/ ...", flush=True)
    if not compileall.compile_file("app.py", quiet=1):
        print("[P0] FAIL: app.py compilation failed.", flush=True)
        return 1
    for directory in ("src", "tests"):
        if not compileall.compile_dir(directory, quiet=1, force=True):
            print(f"[P0] FAIL: compilation failed under {directory}/.", flush=True)
            return 1

    print("[P0] Running targeted deterministic tests (no model training, no live AIS network).", flush=True)
    result = pytest.main(["-q", *P0_TESTS])
    if int(result) != 0:
        print("[P0] TARGETED_VALIDATION=FAIL", flush=True)
        return int(result)
    print("[P0] TARGETED_VALIDATION=PASS", flush=True)
    print("[P0] Live-network acceptance and the complete repository suite remain separate gates.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
