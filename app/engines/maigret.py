"""maigret adapter — broadest username coverage, writes a JSON report file."""
from __future__ import annotations

import glob
import json
import os
import tempfile

from ..schema import Finding, InputKind
from .base import Emit, Engine, Progress, _noprog, run_cmd


class Maigret(Engine):
    name = "maigret"
    binary = "maigret"
    accepts = (InputKind.username,)

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        # maigret writes results to a JSON file (no live stdout of hits), so its
        # findings necessarily arrive as a batch when the scan completes.
        findings: list[Finding] = []
        with tempfile.TemporaryDirectory(prefix="maigret_") as out:
            cmd = [
                self.exe(), target,
                "-a",                    # scan ALL sites (default is only top-500)
                "--retries", "1",        # one retry so contention timeouts don't drop hits
                "--no-progressbar", "--no-color",
                "--timeout", "30",       # give slow sites room under parallel load
                "-J", "simple",          # write simple json report
                "-fo", out,
            ]
            # maigret is the deep engine (thousands of sites); it batches at the end,
            # so give it a generous outer ceiling. Users can Stop early if needed.
            await run_cmd(cmd, timeout=420)
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
