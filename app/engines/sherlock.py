"""sherlock adapter — fast username confirm, parse [+] lines from stdout."""
from __future__ import annotations

import re

from ..schema import Finding, InputKind
from .base import Emit, Engine, run_cmd

# sherlock prints found hits as: [+] SiteName: https://...
_HIT = re.compile(r"^\[\+\]\s*([^:]+):\s*(https?://\S+)", re.MULTILINE)


class Sherlock(Engine):
    name = "sherlock"
    binary = "sherlock"
    accepts = (InputKind.username,)

    async def run(self, target: str, kind: InputKind, emit: Emit) -> list[Finding]:
        cmd = [
            self.exe(), target,
            "--no-color", "--print-found", "--timeout", "20",
        ]
        rc, stdout, stderr = await run_cmd(cmd, timeout=300)
        out: list[Finding] = []
        for site, url in _HIT.findall(stdout):
            f = Finding(
                source=self.name, kind="account", site=site.strip(),
                url=url.strip(), value=target, found=True, confidence=0.75,
            )
            out.append(f)
            await emit(f)
        return out
