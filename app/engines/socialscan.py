"""socialscan adapter — definitive account-existence checks (username + email).

socialscan queries a small set of major platforms (GitHub, GitLab, Instagram,
Pinterest, Reddit, Twitter, Tumblr, Firefox) and — unlike heuristic username
scanners — distinguishes "taken" from "available" authoritatively. It also
accepts email addresses, adding an email->platform signal beyond holehe.
"""
from __future__ import annotations

import json
import os
import tempfile

from ..schema import Finding, InputKind
from .base import Emit, Engine, Progress, _noprog, run_cmd


def parse_report(data: dict, target: str, source: str) -> list[Finding]:
    """A definitive hit = query succeeded, is valid, and the handle is taken."""
    out: list[Finding] = []
    for _query, entries in (data or {}).items():
        for e in entries:
            if not isinstance(e, dict):
                continue
            if (str(e.get("success")) == "True" and str(e.get("valid")) == "True"
                    and str(e.get("available")) == "False"):
                out.append(Finding(
                    source=source, kind="account", site=str(e.get("platform", "?")),
                    url=e.get("link"), value=target, found=True, confidence=0.85,
                    extra={"note": "account confirmed to exist"},
                ))
    return out


class SocialScan(Engine):
    name = "socialscan"
    binary = "socialscan"
    accepts = (InputKind.username, InputKind.email)

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        with tempfile.TemporaryDirectory(prefix="socialscan_") as d:
            jf = os.path.join(d, "ss.json")
            await run_cmd([self.exe(), target, "--json", jf], timeout=90)
            try:
                with open(jf, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                return []
        out = parse_report(data, target, self.name)
        for f in out:
            await emit(f)
        await progress({"found": len(out)})
        return out
