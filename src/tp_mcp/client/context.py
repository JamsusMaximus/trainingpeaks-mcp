"""Context variable for coach account athlete targeting."""

import contextvars

athlete_override: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "athlete_override", default=None
)
