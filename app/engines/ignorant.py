"""ignorant adapter — checks if a phone number is registered on sites.

By the holehe author (megadose). Tells you whether a phone number has an account
on Instagram, Amazon, Snapchat, etc. — a data dimension phoneinfoga (carrier /
dorks) doesn't cover. Needs the number split into country-code + national part.
"""
from __future__ import annotations

import re

from ..schema import Finding, InputKind
from .base import Emit, Engine, Progress, _noprog, run_cmd

# ignorant prints:  [+] site.com (used) / [-] not used / [x] rate-limited
_USED = re.compile(r"^\[\+\]\s*([\w.-]+\.[a-z]{2,})\b", re.IGNORECASE)


class Ignorant(Engine):
    name = "ignorant"
    binary = "ignorant"
    accepts = (InputKind.phone,)

    def _split(self, target: str):
        """Return (country_code, national_number) or None if not parseable."""
        try:
            import phonenumbers
            num = target if target.strip().startswith("+") else "+" + re.sub(r"[^\d]", "", target)
            n = phonenumbers.parse(num, None)
            if not phonenumbers.is_possible_number(n):
                return None
            return str(n.country_code), str(n.national_number)
        except Exception:
            return None

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        parts = self._split(target)
        if not parts:
            return []   # needs an international number with a country code
        cc, national = parts
        out: list[Finding] = []

        async def on_line(line: str):
            m = _USED.match(line.strip())
            if not m:
                return
            f = Finding(source=self.name, kind="account", site=m.group(1).strip(),
                        url=None, value=target, found=True, confidence=0.7,
                        extra={"note": "phone number registered on this site"})
            out.append(f)
            await emit(f)
            await progress({"found": len(out)})

        cmd = [self.exe(), cc, national, "--only-used", "--no-color"]
        await run_cmd(cmd, timeout=120, on_line=on_line)
        return out
