"""Regression tests for Streamlit UI package startup side effects."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_importing_ui_package_does_not_emit_streamlit_commands() -> None:
    """Importing src.ui must not render components before app configuration."""
    script = r"""
import streamlit as st
import streamlit.components.v1 as components
from unittest.mock import Mock

st.html = Mock(side_effect=AssertionError("st.html called during src.ui import"))
components.html = Mock(side_effect=AssertionError("components.html called during src.ui import"))

import src.ui  # noqa: F401

st.html.assert_not_called()
components.html.assert_not_called()
"""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) if not existing else str(ROOT) + os.pathsep + existing
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        "Importing src.ui executed a Streamlit command or failed unexpectedly:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_sidebar_controller_is_installed_after_page_configuration() -> None:
    """The app must configure its page before invoking the browser controller."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    config_index = source.index("st.set_page_config(")
    install_index = source.index("_install_floating_sidebar_controller()", config_index)
    css_index = source.index("inject_css()", config_index)
    assert config_index < install_index < css_index
