# OSINT Finder

One web UI that fans a single identifier — **username, email, phone, or full name** —
out to multiple best-in-class OSINT engines, streams results live, correlates them,
and gives you one combined report.

It does **not** reimplement anything. It orchestrates existing tools via subprocess,
normalizes their output into one schema, and pivots discovered identifiers back in.

```
 input ──▶ detect kind ──▶ fan to engines ──▶ normalize ──▶ dedup ──▶ pivot ──▶ report
                           maigret / sherlock / holehe / phoneinfoga
```

## Engines

| Engine | Input | Role | Install |
|--------|-------|------|---------|
| [maigret](https://github.com/soxoj/maigret)         | username | 3000+ sites + profile data | `pip` |
| [sherlock](https://github.com/sherlock-project/sherlock) | username | fast 400+ site confirm | `pip` |
| [gosearch](https://github.com/ibnaleem/gosearch)    | username | 300+ sites + **info-stealer breach check** (HudsonRock) | binary → `./bin` |
| [holehe](https://github.com/megadose/holehe)        | email    | which sites an email is registered on | `pip` |
| [phoneinfoga](https://github.com/sundowndev/phoneinfoga) | phone | country/carrier + Google dork links | binary → `./bin`, or Docker |

Engines are resolved from `PATH`, the venv `Scripts/` dir, and the project `./bin`.
Any engine not found is auto-skipped (shown greyed-out in the UI). Breach hits are
highlighted red in the results table.

### Standalone binaries (gosearch, phoneinfoga)
Both are Go binaries. Fetch prebuilt Windows releases into `./bin`:

```powershell
.\scripts\fetch-binaries.ps1
```

**phoneinfoga via Docker** (alternative — no binary needed): if `phoneinfoga` is not
in `./bin`/PATH but `docker` is present, the engine automatically runs
`docker run --rm sundowndev/phoneinfoga scan -n <number>`.

## Correlation / pivot

- **email** → the local part (`ravi.kumar@x.com` → `ravi.kumar`) is re-run through username engines.
- **name** → generates handle variants (`ravikumar`, `ravi.kumar`, `ravi_kumar`) and runs the top 2.
- Results from every engine are deduped by `(site, url, value)`.

## Setup

```powershell
# from the project root
.\run.ps1            # creates .venv, installs deps, starts server
```

Then open <http://127.0.0.1:8000>.

For gosearch + phoneinfoga, also run `.\scripts\fetch-binaries.ps1` once (see above).

## Removal Assistant

After a search, tick the accounts you own and click **Removal plan**. For each
selected account the app returns:

- the platform's **direct account-deletion link** + difficulty (easy/medium/hard/impossible)
- a pre-drafted **GDPR Art.17 / India DPDP 2023 "right to erasure"** email you can send

It does **not** delete anything automatically — no platform lets an outside app
delete an account without your login and its own confirmation flow. This is
guidance + request-generation only. Breach/leak findings are excluded (you can't
"delete" a leak — rotate those passwords and enable 2FA).

Deletion recipes live in [`app/data/removal_db.json`](app/data/removal_db.json)
(inspired by justdelete.me); unknown sites fall back to generic settings + an
erasure request.

## Notes / limits
- **Python 3.14**: some engines may lack wheels yet. If `pip install` fails for one,
  the app still runs — that engine just shows as missing. Pin `python 3.11–3.12` if needed.
- holehe / gosearch upstreams move fast; parsers here are best-effort against current CLI output.

## ⚠️ Legal & ethics
Use only against targets you are **authorized** to investigate — your own accounts,
consented subjects, sanctioned pentest scope, or lawful investigations.
No Aadhaar/PAN/voter-ID/bank lookups — those are illegal under India's IT Act & DPDP Act 2023.
Public-profile OSINT only. You are responsible for how you use this.
