"""holehe adapter — which sites an email is registered on (no email sent)."""
from __future__ import annotations

import re

from ..schema import Finding, InputKind
from .base import Emit, Engine, run_cmd

# holehe prints:  [+] site.com   (used)   /  [-] site.com (not used).
# Require a dot so footer/summary lines like "[+] Email" are not treated as sites.
_USED = re.compile(r"^\[\+\]\s*([\w.-]+\.[a-z]{2,})\b", re.MULTILINE | re.IGNORECASE)


class Holehe(Engine):
    name = "holehe"
    binary = "holehe"
    accepts = (InputKind.email,)

    async def run(self, target: str, kind: InputKind, emit: Emit) -> list[Finding]:
        cmd = [self.exe(), target, "--only-used", "--no-color"]
        rc, stdout, stderr = await run_cmd(cmd, timeout=240)
        out: list[Finding] = []
        for site in _USED.findall(stdout):
            f = Finding(
                source=self.name, kind="account", site=site.strip(),
                url=None, value=target, found=True, confidence=0.7,
                extra={"note": "email registered on this site"},
            )
            out.append(f)
            await emit(f)
        return out
