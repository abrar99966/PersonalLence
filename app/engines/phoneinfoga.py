"""phoneinfoga adapter — phone recon (country + carrier + Google dork links).

Resolution order:
  1. `phoneinfoga` binary on PATH / venv / ./bin
  2. Docker fallback: `docker run --rm sundowndev/phoneinfoga scan -n <number>`

phoneinfoga v2 prints a "Results for local" block (Country/Local/E164) plus a
"Results for googlesearch" block of dork URLs.
"""
from __future__ import annotations

import re
import shutil

from ..schema import Finding, InputKind
from .base import Emit, Engine, Progress, _noprog, run_cmd

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_FIELD = {
    "country": re.compile(r"^Country:\s*(.+)$", re.I | re.M),
    "carrier": re.compile(r"^Carrier:\s*(.+)$", re.I | re.M),
    "line_type": re.compile(r"^Line type:\s*(.+)$", re.I | re.M),
    "local": re.compile(r"^Local:\s*(.+)$", re.I | re.M),
    "e164": re.compile(r"^E164:\s*(.+)$", re.I | re.M),
    "international": re.compile(r"^International:\s*(.+)$", re.I | re.M),
}
_URL = re.compile(r"https?://\S+")


class PhoneInfoga(Engine):
    name = "phoneinfoga"
    binary = "phoneinfoga"
    accepts = (InputKind.phone,)

    def _docker_available(self) -> bool:
        return shutil.which("docker") is not None

    def available(self) -> bool:
        return super().available() or self._docker_available()

    def _build_cmd(self, target: str) -> list[str]:
        exe = self.exe()
        if exe:
            return [exe, "scan", "-n", target]
        # Docker fallback (honors "run phoneinfoga via Docker")
        return ["docker", "run", "--rm", "sundowndev/phoneinfoga", "scan", "-n", target]

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        rc, stdout, stderr = await run_cmd(self._build_cmd(target), timeout=180)
        blob = _ANSI.sub("", stdout + "\n" + stderr)

        extra: dict = {}
        for key, rx in _FIELD.items():
            m = rx.search(blob)
            if m:
                extra[key] = m.group(1).strip()
        dorks = _URL.findall(blob)
        if dorks:
            extra["dorks"] = dorks[:25]

        f = Finding(
            source=self.name, kind="phone", site="phoneinfoga",
            url=None, value=target, found=bool(extra), confidence=0.6,
            extra=extra or {"note": "no data returned", "raw": blob[:500]},
        )
        await emit(f)
        await progress({"found": 1 if extra else 0})
        return [f]
