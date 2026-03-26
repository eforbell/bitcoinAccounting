"""Shared API model base types for the web layer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base model with strict-ish API defaults."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )
