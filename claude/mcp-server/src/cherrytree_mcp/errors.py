"""Errors that are reported back to Claude as tool errors (messages are user-facing)."""

from __future__ import annotations


class NotebookError(Exception):
    """Base class: anything Claude should see as a readable tool error."""


class PageNotFound(NotebookError):
    pass


class AmbiguousPage(NotebookError):
    pass


class InvalidRequest(NotebookError):
    pass


class UnsafeWrite(NotebookError):
    pass
