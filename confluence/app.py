"""Entrypoint glue module for the Python Confluence stack.

Bridges to the internal packages added previously in this repo while matching
the requested folder layout. Prefer calling via CLI or API modules.
"""

from __future__ import annotations

from confluence.server.app import app as fastapi_app  # re-export

__all__ = ["fastapi_app"]

