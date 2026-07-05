"""sherlock adapter — streams found usernames live as it scans."""
from __future__ import annotations

import re

from ..schema import Finding, InputKind
from .base import Emit, Engine, Progress, _noprog, run_cmd

# sherlock prints found hits as: [+] SiteName: https://...
_HIT = re.compile(r"^\[\+\]\s*([^:]+):\s*(https?://\S+)")


class Sherlock(Engine):
    name = "sherlock"
    binary = "sherlock"
    accepts = (InputKind.username,)

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        out: list[Finding] = []

        async def on_line(line: str):
            m = _HIT.match(line.strip())
            if not m:
                return
            f = Finding(source=self.name, kind="account", site=m.group(1).strip(),
                        url=m.group(2).strip(), value=target, found=True, confidence=0.75)
            out.append(f)
            await emit(f)
            await progress({"found": len(out)})

        cmd = [self.exe(), target, "--no-color", "--print-found", "--timeout", "12"]
        await run_cmd(cmd, timeout=240, on_line=on_line)
        return out
