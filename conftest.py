"""
Pytest configuration.

This file exists to put the repository root on ``sys.path``. Imports in this
codebase are absolute (``from src....``) and there are no ``__init__.py`` files,
so everything is run from the repository root as a module. Pytest prepends the
directory of the root ``conftest.py`` to ``sys.path``, which makes ``pytest``
behave like ``python -m pytest`` and keeps the tests importable either way.
"""

from __future__ import annotations
