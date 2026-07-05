"""HudsonRock adapter — info-stealer breach intel for an EMAIL.

Uses HudsonRock's free Cavalier OSINT API (no key). Tells you whether an email's
credentials were captured by info-stealer malware, with the compromise date and
scale — a data dimension no other engine here covers (gosearch's HudsonRock check
is username-only). Pure HTTP: no subprocess, so it runs anywhere and never hammers
target sites.
"""
from __future__ import annotations

from ..schema import Finding, InputKind
from .base import Emit, Engine, Progress, _noprog

_API = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email"


class HudsonRock(Engine):
    name = "hudsonrock"
    binary = ""                      # HTTP API, no CLI/binary
    accepts = (InputKind.email,)

    def available(self) -> bool:
        return True                  # network-based; always "installed"

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(_API, params={"email": target})
            data = r.json()
        except Exception:
            return []

        stealers = data.get("stealers") or []
        message = (data.get("message") or "").strip()
        if not stealers and "infected" not in message.lower():
            return []                # clean — nothing to report

        latest = stealers[0] if stealers else {}
        extra = {
            "alert": f"email found in {len(stealers) or 'a'} info-stealer log(s) — "
                     "credentials at risk; rotate passwords + enable 2FA",
            "stealer_logs": len(stealers),
        }
        if latest.get("date_compromised") and latest["date_compromised"] != "Not Found":
            extra["date_compromised"] = latest["date_compromised"]
        if data.get("total_user_services"):
            extra["exposed_services"] = data["total_user_services"]

        f = Finding(
            source=self.name, kind="breach", site="HudsonRock (email)",
            url="https://www.hudsonrock.com/free-tools", value=target,
            found=True, confidence=0.9, extra=extra,
        )
        await emit(f)
        await progress({"found": 1})
        return [f]
