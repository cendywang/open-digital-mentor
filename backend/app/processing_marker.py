"""Sentinel used to close the pipeline's internal event queue.

Its own module so the identity check in `pipeline.run` can never be defeated
by a reimport creating a second object.
"""

from __future__ import annotations


class _TurnDone:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<TURN_DONE>"


TURN_DONE = _TurnDone()
