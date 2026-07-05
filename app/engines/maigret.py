"""maigret adapter — broadest username coverage, writes a JSON report file."""
from __future__ import annotations

import glob
import json
import os
import tempfile

from ..schema import Finding, InputKind
from .base import Emit, Engine, run_cmd


class Maigret(Engine):
    name = "maigret"
    binary = "maigret"
    accepts = (InputKind.username,)

    async def run(self, target: str, kind: InputKind, emit: Emit) -> list[Finding]:
        findings: list[Finding] = []
        with tempfile.TemporaryDirectory(prefix="maigret_") as out:
            cmd = [
                self.exe(), target,
                "--no-progressbar", "--no-color",
                "--timeout", "30",
                "-J", "simple",          # write simple json report
                "-fo", out,
            ]
            rc, stdout, stderr = await run_cmd(cmd, timeout=300)
            for path in glob.glob(os.path.join(out, "**", "*.json"), recursive=True):
                findings += await self._parse_report(path, target, emit)
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
