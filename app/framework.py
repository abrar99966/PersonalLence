"""OSINT Framework integration — curated manual pivots per input kind.

These are human-curated resources (websites, tools, dorks) from the OSINT
Framework (https://osintframework.com, MIT). They are NOT automatable, so we
surface them as an 'explore further' list contextual to the detected input type,
extending the app's reach far beyond the automated engines.
"""
from __future__ import annotations

import json
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "data" / "osint_framework.json").read_text(encoding="utf-8"))
_RESOURCES: list[dict] = _DATA["resources"]
SOURCE = _DATA["_source"]


def suggest(kind: str, free_only: bool = False, limit: int = 60) -> dict:
    """Curated OSINT-Framework resources relevant to a detected input kind."""
    items = [r for r in _RESOURCES if kind in r["kinds"]]
    if free_only:
        items = [r for r in items if r["pricing"] == "free" and not r["registration"]]
    items = items[:limit]
    # group by category for display
    groups: dict[str, list[dict]] = {}
    for r in items:
        groups.setdefault(r["category"], []).append(r)
    return {
        "kind": kind,
        "count": len(items),
        "groups": [{"category": c, "resources": rs} for c, rs in groups.items()],
        "source": SOURCE,
    }
