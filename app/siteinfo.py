"""Describe what a platform is, so the results 'Info' column is never empty."""
from __future__ import annotations

import json
from pathlib import Path

from .removal import registrable_domain

_INFO: dict = json.loads((Path(__file__).parent / "data" / "site_info.json").read_text(encoding="utf-8"))


def describe(site: str, url: str | None) -> str | None:
    """Return a short 'what is this site' blurb, or None if unknown."""
    domain = registrable_domain(url, site)
    desc = _INFO.get(domain)
    if desc:
        return desc
    # some sites live on subdomains not caught by registrable_domain (e.g. hub.docker.com)
    if url:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        for key, val in _INFO.items():
            if key.startswith("_"):
                continue
            if host.endswith(key):
                return val
    return None
