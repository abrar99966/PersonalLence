"""maigret adapter — broadest username coverage, writes a JSON report file."""
from __future__ import annotations

import glob
import json
import os
import tempfile

import os

from ..schema import Finding, InputKind
from .base import Emit, Engine, Progress, _noprog, deep_scan, run_cmd

# Default when a request doesn't specify: deep (all sites) for local richness.
# The cloud deploy sets MAIGRET_DEEP=false so the free tier stays light.
_DEEP_DEFAULT = os.getenv("MAIGRET_DEEP", "true").lower() in ("1", "true", "yes")


class Maigret(Engine):
    name = "maigret"
    binary = "maigret"
    accepts = (InputKind.username,)

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        # maigret writes results to a JSON file (no live stdout of hits), so its
        # findings necessarily arrive as a batch when the scan completes.
        override = deep_scan.get()
        deep = _DEEP_DEFAULT if override is None else bool(override)

        findings: list[Finding] = []
        with tempfile.TemporaryDirectory(prefix="maigret_") as out:
            cmd = [self.exe(), target, "--no-progressbar", "--no-color",
                   "-J", "simple", "-fo", out]
            if deep:                                  # all ~3000 sites, resilient
                cmd += ["-a", "--retries", "1", "--timeout", "30"]
                ceiling = 420
            else:                                     # fast: top-500, lighter (free tier)
                cmd += ["--top-sites", "500", "--timeout", "20"]
                ceiling = 180
            await run_cmd(cmd, timeout=ceiling)
            for path in glob.glob(os.path.join(out, "**", "*.json"), recursive=True):
                findings += await self._parse_report(path, target, emit)
        await progress({"found": len(findings)})
        return findings

    async def _parse_report(self, path: str, target: str, emit: Emit) -> list[Finding]:
        out: list[Finding] = []
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return out
        # maigret simple report is {sitename: {url_user, status, ...}}
        items = data.items() if isinstance(data, dict) else enumerate(data)
        for site, entry in items:
            if not isinstance(entry, dict):
                continue
            status = entry.get("status")
            ids: dict = {}
            state = ""
            if isinstance(status, dict):
                state = str(status.get("status", "")).lower()
                ids = status.get("ids") or {}
            elif isinstance(status, str):
                state = status.lower()
            if state not in ("claimed", "found", "true"):
                continue
            url = entry.get("url_user") or entry.get("url_main")
            # surface the useful profile fields maigret scraped, if any
            extra = {
                k: ids[k]
                for k in ("fullname", "image", "follower_count", "location", "created_at")
                if k in ids
            }
            tags = (entry.get("site") or {}).get("tags")
            if tags:
                extra["tags"] = tags
            f = Finding(
                source=self.name, kind="account", site=str(site),
                url=url, value=target, found=True, confidence=0.8, extra=extra,
            )
            out.append(f)
            await emit(f)
        return out
