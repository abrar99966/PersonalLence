"""Removal Assistant — turn findings into actionable account-deletion steps.

This does NOT delete anything automatically (impossible without the user's
credentials and each site's own confirmation flow). It provides, per selected
finding:
  * the platform's direct account-deletion URL + difficulty, when known
  * a pre-filled GDPR / India-DPDP "right to erasure" request the user can send
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

_DB_PATH = Path(__file__).parent / "data" / "removal_db.json"
_DB: dict = json.loads(_DB_PATH.read_text(encoding="utf-8"))

_DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2, "impossible": 3, "unknown": 4}


def registrable_domain(url: str | None, site: str) -> str:
    """Best-effort registrable domain from a URL, falling back to the site name."""
    host = ""
    if url:
        host = (urlparse(url).hostname or "").lower()
    if not host:
        return site.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    # keep known multi-label instances intact (e.g. mastodon.social), else last 2
    if host in _DB:
        return host
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def erasure_email(site: str, url: str | None, domain: str, requester: str) -> dict:
    """Draft a GDPR Art.17 / DPDP 2023 right-to-erasure request."""
    to = f"privacy@{domain}"
    subject = f"Right to Erasure Request — account removal on {site}"
    body = (
        "Hello,\n\n"
        "Under the EU GDPR (Article 17) and India's Digital Personal Data "
        "Protection Act 2023, I request permanent erasure of all personal data "
        "associated with the following account/profile, and closure of the account:\n\n"
        f"  Platform : {site}\n"
        f"  Profile  : {url or '(see username on your platform)'}\n\n"
        "Please confirm deletion within 30 days as required by law. If this is not "
        "the correct data-protection contact, kindly forward this to your Data "
        "Protection Officer.\n\n"
        "Regards,\n"
        f"{requester or '[Your Name]'}"
    )
    return {"to": to, "subject": subject, "body": body}


def plan_for_finding(finding: dict, requester: str = "") -> dict:
    """Build one removal step for a single finding dict."""
    site = str(finding.get("site") or "unknown")
    url = finding.get("url")
    domain = registrable_domain(url, site)
    info = _DB.get(domain)

    if info:
        step = {
            "site": site,
            "profile_url": url,
            "domain": domain,
            "difficulty": info["difficulty"],
            "delete_url": info["url"],
            "notes": info["notes"],
            "known": True,
        }
    else:
        step = {
            "site": site,
            "profile_url": url,
            "domain": domain,
            "difficulty": "unknown",
            "delete_url": f"https://{domain}/settings" if domain else None,
            "notes": "No deletion recipe on file. Log in, open account settings, look "
                     "for 'delete/close/deactivate account', or send the erasure request.",
            "known": False,
        }
    step["erasure_email"] = erasure_email(site, url, domain, requester)
    return step


def build_removal_plan(findings: list[dict], requester: str = "") -> dict:
    """Build removal steps for many findings, sorted easy-first, deduped by domain."""
    seen: set[str] = set()
    steps: list[dict] = []
    for f in findings:
        # breach findings aren't accounts to delete — skip, they need a different path
        if f.get("kind") == "breach":
            continue
        step = plan_for_finding(f, requester)
        key = step["domain"] + "|" + (step["profile_url"] or "")
        if key in seen:
            continue
        seen.add(key)
        steps.append(step)
    steps.sort(key=lambda s: _DIFFICULTY_RANK.get(s["difficulty"], 4))
    return {
        "count": len(steps),
        "steps": steps,
        "disclaimer": (
            "This tool cannot delete accounts for you — each platform requires your "
            "own login and confirmation. Only act on accounts you actually own. "
            "Breach/leak findings cannot be 'deleted'; change those passwords everywhere "
            "and enable 2FA."
        ),
    }
