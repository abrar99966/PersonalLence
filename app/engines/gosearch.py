"""gosearch adapter — username across 300+ sites + info-stealer breach check.

gosearch is a standalone Go binary (shipped in ./bin). Its value over sherlock is
the HudsonRock info-stealer breach lookup. Output is ANSI-colored text.
"""
from __future__ import annotations

import re
import tempfile

from ..schema import Finding, InputKind
from .base import Emit, Engine, Progress, _noprog, run_cmd

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# found profile line:  [+] SiteName:https://...   (gosearch prints no space after ':')
# `↳` marks GitHub sub-detail lines (e.g. "[+] ↳ Avatar URL:https://...") — exclude them.
_HIT = re.compile(r"^\[\+\]\s*([^:↳]+):\s*(https?://\S+)")
# HudsonRock info-stealer marker (only printed when compromised)
_BREACH = re.compile(r"Info-stealer compromise detected", re.IGNORECASE)
# ProxyNova leaked-password hits:  [+] Found 77 compromised passwords for <user>:
_PROXYNOVA = re.compile(r"Found\s+(\d+)\s+compromised passwords", re.IGNORECASE)


class GoSearch(Engine):
    name = "gosearch"
    binary = "gosearch"
    accepts = (InputKind.username,)

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        out: list[Finding] = []
        full: list[str] = []

        async def on_line(raw: str):
            line = _ANSI.sub("", raw).rstrip("\n")
            full.append(line)
            m = _HIT.match(line.strip())
            if m:
                f = Finding(source=self.name, kind="account", site=m.group(1).strip(),
                            url=m.group(2).strip(), value=target, found=True, confidence=0.75)
                out.append(f)
                await emit(f)
                await progress({"found": len([n for n in out if n.kind == "account"])})

        cmd = [self.exe(), "-u", target, "--no-false-positives"]
        # gosearch writes <username>.txt reports into cwd — run in a temp dir so it
        # never litters the project or leaks scan data to disk.
        with tempfile.TemporaryDirectory(prefix="gosearch_") as work:
            await run_cmd(cmd, cwd=work, timeout=300, on_line=on_line)

        text = "\n".join(full)
        if _BREACH.search(text):
            f = Finding(source=self.name, kind="breach", site="HudsonRock",
                        url="https://www.hudsonrock.com/", value=target, found=True, confidence=0.9,
                        extra={"alert": "info-stealer compromise detected — credentials may be exposed"})
            out.append(f)
            await emit(f)
        m = _PROXYNOVA.search(text)
        if m:
            count = int(m.group(1))
            f = Finding(source=self.name, kind="breach", site="ProxyNova",
                        url="https://www.proxynova.com/tools/comb", value=target, found=True,
                        confidence=0.85,
                        extra={"alert": f"{count} compromised password(s) found in leak databases",
                               "count": count})
            out.append(f)
            await emit(f)
        return out
