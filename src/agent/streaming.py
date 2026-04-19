"""Utilities for publishing runtime progress events during graph execution."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

StreamCallback = Callable[[str, dict[str, Any]], None]

_stream_callback: ContextVar[StreamCallback | None] = ContextVar("stream_callback", default=None)


@contextmanager
def use_stream_callback(callback: StreamCallback | None) -> Iterator[None]:
    token = _stream_callback.set(callback)
    try:
        yield
    finally:
        _stream_callback.reset(token)


def emit_stream_event(event: str, payload: dict[str, Any]) -> None:
    callback = _stream_callback.get()
    if callback is None:
        return
    callback(event, payload)

