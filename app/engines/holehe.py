"""holehe adapter — which sites an email is registered on (no email sent)."""
from __future__ import annotations

import re

from ..schema import Finding, InputKind
from .base import Emit, Engine, Progress, _noprog, run_cmd

# holehe prints:  [+] site.com   (used)   /  [-] site.com (not used).
# Require a dot so footer/summary lines like "[+] Email" are not treated as sites.
_USED = re.compile(r"^\[\+\]\s*([\w.-]+\.[a-z]{2,})\b", re.IGNORECASE)


class Holehe(Engine):
    name = "holehe"
    binary = "holehe"
    accepts = (InputKind.email,)

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        out: list[Finding] = []

        async def on_line(line: str):
            m = _USED.match(line.strip())
            if not m:
                return
            f = Finding(source=self.name, kind="account", site=m.group(1).strip(),
                        url=None, value=target, found=True, confidence=0.7,
                        extra={"note": "email registered on this site"})
            out.append(f)
            await emit(f)
            await progress({"found": len(out)})

        cmd = [self.exe(), target, "--only-used", "--no-color"]
        await run_cmd(cmd, timeout=240, on_line=on_line)
        return out
