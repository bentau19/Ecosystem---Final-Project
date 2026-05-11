"""
Native module entry point.

Re-exports ``Client`` and ``Server`` from ``native.windows.pipe`` so that
both ``from native import Client`` and ``from native.windows.pipe import Client``
resolve identically.
"""

from native.windows.pipe import Client, Server  # noqa: F401

__all__ = ["Client", "Server"]
