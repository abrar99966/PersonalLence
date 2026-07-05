"""Offline unit tests — no network, no engine binaries required."""
import asyncio
import json
import os
import tempfile

from app.dispatcher import (
    detect,
    is_safe,
    username_candidates_from_name,
    username_from_email,
)
from app.engines.gosearch import _BREACH, _PROXYNOVA, _HIT as _GO_HIT
from app.engines.holehe import _USED
from app.engines.maigret import Maigret
from app.engines.phoneinfoga import PhoneInfoga, _FIELD
from app.engines.sherlock import _HIT
from app.removal import build_removal_plan, plan_for_finding, registrable_domain
from app.schema import InputKind
from app.engines.ignorant import _USED as _IG_USED, Ignorant
from app.engines.socialscan import parse_report as ss_parse
from app.framework import suggest as framework_suggest
from app.siteinfo import describe


# ---------------- detection ----------------

def test_detect_email():
    assert detect("ravi.kumar@gmail.com") is InputKind.email

def test_detect_phone_variants():
    assert detect("+91 98765 43210") is InputKind.phone
    assert detect("9876543210") is InputKind.phone

def test_detect_username():
    assert detect("ibnaleem") is InputKind.username

def test_detect_name():
    assert detect("Ravi Kumar") is InputKind.name


# ---------------- safety guard (argv injection) ----------------

def test_is_safe_rejects_flags():
    assert not is_safe("--proxy=evil")
    assert not is_safe("-o /etc/passwd")

def test_is_safe_rejects_control_chars():
    assert not is_safe("foo\nbar")
    assert not is_safe("x" * 300)
    assert not is_safe("   ")

def test_is_safe_accepts_normal():
    assert is_safe("ibnaleem")
    assert is_safe("ravi.kumar@gmail.com")
    assert is_safe("+91 98765 43210")


# ---------------- pivots ----------------

def test_name_candidates():
    assert username_candidates_from_name("Ravi Kumar")[0] == "ravikumar"
    assert "ravi.kumar" in username_candidates_from_name("Ravi Kumar")

def test_username_from_email():
    assert username_from_email("ravi.kumar@x.com") == "ravi.kumar"


# ---------------- parsers ----------------

def test_sherlock_regex():
    # engines now match per streamed line
    lines = ["[+] GitHub: https://github.com/x", "[+] Twitter: https://twitter.com/x", "[-] Nope: https://n/x"]
    hits = [m.groups() for m in (_HIT.match(l) for l in lines) if m]
    assert len(hits) == 2
    assert hits[0][0].strip() == "GitHub"

def test_holehe_regex_filters_non_domains():
    lines = ["[+] amazon.com", "[+] twitter.com", "[+] Email", "[+] Github"]
    sites = [m.group(1) for m in (_USED.match(l) for l in lines) if m]
    assert "amazon.com" in sites
    assert "twitter.com" in sites
    assert "Email" not in sites   # footer noise must be dropped
    assert "Github" not in sites  # no dot -> not a domain

def test_gosearch_found_and_breach():
    out = (
        "\x1b[32m[+] GitHub: https://github.com/x\x1b[0m\n"
        "[?] Maybe: https://maybe/x\n"
        "[+] ↳ Avatar URL:https://avatars/x\n"
        "‼ Info-stealer compromise detected\n"
        "[+] Found 77 compromised passwords for x:\n"
    )
    clean = out.replace("\x1b[32m", "").replace("\x1b[0m", "")
    hits = [(m.group(1).strip(), m.group(2)) for m in (_GO_HIT.match(l.strip()) for l in clean.splitlines()) if m]
    assert ("GitHub", "https://github.com/x") in hits
    assert not any("↳" in s or "Avatar" in s for s, _ in hits)  # sub-detail excluded
    assert _BREACH.search(out)
    assert int(_PROXYNOVA.search(out).group(1)) == 77

def test_phoneinfoga_v2_fields():
    blob = (
        "Results for local\nRaw local: 4152007986\nLocal: (415) 200-7986\n"
        "E164: +14152007986\nInternational: 14152007986\nCountry: US\n"
    )
    assert _FIELD["country"].search(blob).group(1).strip() == "US"
    assert _FIELD["e164"].search(blob).group(1).strip() == "+14152007986"
    assert _FIELD["local"].search(blob).group(1).strip() == "(415) 200-7986"

def test_phoneinfoga_available_via_docker(monkeypatch):
    import app.engines.phoneinfoga as mod
    eng = PhoneInfoga()
    monkeypatch.setattr(eng, "exe", lambda: None)               # no binary
    monkeypatch.setattr(mod.shutil, "which", lambda n: "/docker")  # docker present
    assert eng.available() is True
    assert eng._build_cmd("+1")[0] == "docker"

def test_framework_suggest():
    for kind in ("username", "email", "phone", "name"):
        r = framework_suggest(kind)
        assert r["kind"] == kind
        assert r["count"] > 0
        # every returned resource is tagged for this kind
        for g in r["groups"]:
            for res in g["resources"]:
                assert kind in res["kinds"]
    # free_only really filters out paid / signup resources
    free = framework_suggest("username", free_only=True)
    for g in free["groups"]:
        for res in g["resources"]:
            assert res["pricing"] == "free" and not res["registration"]

def test_ignorant_regex_and_split():
    lines = ["[+] amazon.com", "[+] instagram.com", "[x] snapchat.com", "[-] nope.com"]
    used = [m.group(1) for m in (_IG_USED.match(l) for l in lines) if m]
    assert used == ["amazon.com", "instagram.com"]   # only [+], drop [x]/[-]
    assert Ignorant()._split("+14152007986") == ("1", "4152007986")
    assert Ignorant()._split("+919876543210") == ("91", "9876543210")

def test_socialscan_parse_report():
    data = {"ibnaleem": [
        {"platform": "Twitter", "available": "False", "valid": "True", "success": "True",
         "link": "https://twitter.com/ibnaleem"},                       # taken -> hit
        {"platform": "GitHub", "available": "True", "valid": "True", "success": "True"},   # available -> skip
        {"platform": "Reddit", "available": "False", "valid": "False", "success": "False"},  # error -> skip
    ]}
    out = ss_parse(data, "ibnaleem", "socialscan")
    assert len(out) == 1
    assert out[0].site == "Twitter"
    assert out[0].url == "https://twitter.com/ibnaleem"

def test_describe_sites():
    assert "Code hosting" in describe("GitHub", "https://github.com/x")
    assert describe("Docker Hub", "https://hub.docker.com/u/x")          # subdomain match
    assert "chess" in describe("Chess", "https://www.chess.com/member/x").lower()
    assert describe("Nonexistent", "https://nope-xyz.qqq/x") is None

def test_registrable_domain():
    assert registrable_domain("https://www.instagram.com/x", "Instagram") == "instagram.com"
    assert registrable_domain("https://mastodon.social/@x", "Mastodon Social") == "mastodon.social"
    assert registrable_domain(None, "GitHub") == "github"

def test_plan_known_and_unknown_site():
    known = plan_for_finding({"site": "Instagram", "url": "https://instagram.com/x", "kind": "account"})
    assert known["known"] is True
    assert known["difficulty"] == "medium"
    assert "remove" in known["delete_url"]
    assert "GDPR" in known["erasure_email"]["body"] or "erasure" in known["erasure_email"]["subject"].lower()

    unknown = plan_for_finding({"site": "Weirdsite", "url": "https://weirdsite.io/x", "kind": "account"})
    assert unknown["known"] is False
    assert unknown["difficulty"] == "unknown"

def test_build_removal_plan_skips_breach_and_sorts():
    findings = [
        {"site": "Instagram", "url": "https://instagram.com/x", "kind": "account"},   # medium
        {"site": "GitHub", "url": "https://github.com/x", "kind": "account"},         # easy
        {"site": "HudsonRock", "url": "h", "kind": "breach"},                          # skipped
        {"site": "GitHub", "url": "https://github.com/x", "kind": "account"},         # dup
    ]
    plan = build_removal_plan(findings, requester="Abrar")
    assert plan["count"] == 2                       # breach skipped, dup removed
    assert plan["steps"][0]["difficulty"] == "easy" # GitHub sorted first
    assert "cannot delete accounts for you" in plan["disclaimer"]
    assert "Abrar" in plan["steps"][0]["erasure_email"]["body"]

def test_maigret_parse_report():
    report = {
        "GitHub": {
            "url_user": "https://github.com/x",
            "site": {"tags": ["coding"]},
            "status": {"status": "Claimed", "ids": {"fullname": "X Y", "follower_count": "10"}},
        },
        "Nope": {"url_user": "https://n/x", "status": {"status": "Available"}},
    }
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "report_x_simple.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(report, fh)

        async def noop(_f):  # emit callback
            return None

        found = asyncio.run(Maigret()._parse_report(p, "x", noop))
    assert len(found) == 1                      # only the Claimed one
    assert found[0].site == "GitHub"
    assert found[0].extra.get("fullname") == "X Y"
    assert found[0].extra.get("tags") == ["coding"]
