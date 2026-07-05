"""FastAPI app: submit a query, poll results, serve the UI."""
from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .dispatcher import is_safe
from .engines import ALL_ENGINES
from .engines.base import current_job, deep_scan, kill_job
from .framework import suggest as framework_suggest
from .orchestrator import orchestrate
from .removal import build_removal_plan
from .schema import RemovalRequest, SearchRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    reaper = asyncio.create_task(_reaper())
    try:
        yield
    finally:
        reaper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reaper


app = FastAPI(title="Parallax", version="1.0", lifespan=lifespan)

# optional Google sign-in gate (active only when GOOGLE_CLIENT_ID is set)
from .auth import setup_auth  # noqa: E402
setup_auth(app)

# limits — this is a local recon tool, but keep it from eating itself
MAX_JOBS = 50            # reject new work past this many live jobs
MAX_CONCURRENT = 8       # concurrent search jobs (each fans out to all its engines)
JOB_TTL = 900            # seconds a job may linger before reaping
MAX_EVENTS = 8000        # bound per-job event buffer

_SEM = asyncio.Semaphore(MAX_CONCURRENT)
_STATIC = Path(__file__).parent / "static"


class Job:
    """Append-only event log the client polls. Robust through proxies/tunnels
    that buffer streaming responses (Cloudflare, etc.) — unlike SSE."""
    __slots__ = ("events", "done", "created", "task")

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.done = False
        self.created = time.monotonic()
        self.task: asyncio.Task | None = None


# in-memory job store: job_id -> Job
_JOBS: dict[str, Job] = {}


async def _reaper() -> None:
    """Drop jobs whose stream was never consumed, so orphans can't leak."""
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        for jid, job in list(_JOBS.items()):
            if now - job.created > JOB_TTL:
                if job.task and not job.task.done():
                    job.task.cancel()
                _JOBS.pop(jid, None)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/api/engines")
async def engines() -> list[dict]:
    return [
        {
            "name": e.name,
            "available": e.available(),
            "accepts": [k.value for k in e.accepts],
        }
        for e in ALL_ENGINES
    ]


@app.post("/api/search")
async def search(req: SearchRequest) -> dict:
    if not is_safe(req.query):
        raise HTTPException(400, "invalid query (empty, too long, or unsafe characters)")
    if len(_JOBS) >= MAX_JOBS:
        raise HTTPException(429, "too many active jobs, try again shortly")

    job_id = uuid.uuid4().hex
    job = Job()
    _JOBS[job_id] = job

    async def sink(event: dict) -> None:
        if event.get("type") == "_eos":
            job.done = True
            return
        if len(job.events) < MAX_EVENTS:
            job.events.append(event)

    async def worker() -> None:
        current_job.set(job_id)   # so run_cmd can register this job's subprocesses
        deep_scan.set(req.deep)   # maigret depth override (None = server default)
        try:
            async with _SEM:  # cap concurrent heavy scans
                await orchestrate(req.query, req.kind, req.pivot, sink)
        except asyncio.CancelledError:
            await sink({"type": "cancelled"})   # user pressed Stop
        except Exception as e:
            await sink({"type": "fatal", "error": str(e)})
        finally:
            await sink({"type": "_eos"})  # marks job.done

    job.task = asyncio.create_task(worker())
    return {"job_id": job_id}


@app.post("/api/cancel/{job_id}")
async def cancel(job_id: str) -> dict:
    """Stop an in-flight search: cancel its task (which kills the subprocesses)."""
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    killed = kill_job(job_id)     # kill subprocesses immediately (don't wait for unwinding)
    if job.task and not job.task.done():
        job.task.cancel()
    return {"cancelled": job_id, "killed": killed}


@app.get("/api/explore/{kind}")
async def explore(kind: str, free_only: bool = False) -> dict:
    """Curated OSINT-Framework resources to manually pursue, by input kind."""
    if kind not in ("username", "email", "phone", "name"):
        raise HTTPException(400, "kind must be username|email|phone|name")
    return framework_suggest(kind, free_only=free_only)


@app.post("/api/removal")
async def removal(req: RemovalRequest) -> dict:
    """Build a deletion/erasure plan for the selected findings.

    Does not delete anything — returns per-platform deletion links, difficulty,
    and a pre-drafted GDPR/DPDP erasure request for each selected account.
    """
    if not req.findings:
        raise HTTPException(400, "no findings selected")
    if len(req.findings) > 500:
        raise HTTPException(400, "too many findings")
    return build_removal_plan(req.findings, req.requester.strip())


@app.get("/api/events/{job_id}")
async def events(job_id: str, since: int = 0) -> dict:
    """Poll new events since index `since`. Client-friendly + proxy-safe (no
    long-lived stream, so Cloudflare/tunnels can't buffer it into oblivion)."""
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    new = job.events[since:]
    resp = {"events": new, "next": since + len(new), "done": job.done}
    if job.done:                       # let the client stop; clean up shortly after
        job.created = time.monotonic() - (JOB_TTL - 30)
    return resp
