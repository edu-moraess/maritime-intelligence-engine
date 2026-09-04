"""Compatibility wrapper for the canonical Overview renderer in ``pages_a``.

The Overview implementation remains in the existing renderer module so legacy
imports continue to work while the workspace layer keeps a single source of
truth for the Overview UI.
"""

from src.ui.pages_a import render_overview

__all__ = ["render_overview"]
