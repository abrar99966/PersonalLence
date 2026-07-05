"""Common data models shared across engines and the API."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InputKind(str, Enum):
    username = "username"
    email = "email"
    phone = "phone"
    name = "name"


class Finding(BaseModel):
    """Normalized result emitted by every engine.

    Whatever an engine outputs is mapped into this shape so the frontend and
    correlation layer only ever deal with one schema.
    """

    source: str                       # engine name, e.g. "maigret"
    kind: str                         # "account" | "profile" | "phone" | "meta"
    site: str                         # platform / site name
    url: str | None = None            # profile url if any
    value: str | None = None          # the identifier that matched (username/email/phone)
    found: bool = True                # engine confirmed presence
    confidence: float = 0.5           # 0..1 rough trust
    extra: dict[str, Any] = Field(default_factory=dict)

    def key(self) -> tuple:
        """Dedup key: same site+url+value from any engine collapses to one."""
        return (self.site.lower(), (self.url or "").lower(), (self.value or "").lower())


class SearchRequest(BaseModel):
    query: str
    kind: InputKind | None = None     # override auto-detection if provided
    pivot: bool = True                # re-feed discovered identifiers back in
    deep: bool | None = None          # maigret depth: True=all sites, None=server default


class RemovalRequest(BaseModel):
    findings: list[dict]              # selected Finding dicts from the results
    requester: str = ""              # name to sign the erasure request with
