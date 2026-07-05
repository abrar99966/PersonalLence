"""FastAPI app: submit a query, stream results over SSE, serve the UI."""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from .dispatcher import is_safe
from .engines import ALL_ENGINES
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


app = FastAPI(title="OSINT Finder", version="1.0", lifespan=lifespan)

# limits — this is a local recon tool, but keep it from eating itself
MAX_JOBS = 50            # reject new work past this many live jobs
MAX_CONCURRENT = 4       # heavy engines (sherlock/maigret) actually running at once
JOB_TTL = 600            # seconds an unconsumed job may linger before reaping
QUEUE_MAX = 5000         # bound per-job queue so a stuck consumer can't balloon memory

_SEM = asyncio.Semaphore(MAX_CONCURRENT)
_STATIC = Path(__file__).parent / "static"


class Job:
    __slots__ = ("queue", "created", "task")

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
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
        # drop events rather than block forever if the consumer is gone
        try:
            job.queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def worker() -> None:
        try:
            async with _SEM:  # cap concurrent heavy scans
                await orchestrate(req.query, req.kind, req.pivot, sink)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await sink({"type": "fatal", "error": str(e)})
        finally:
            await sink({"type": "_eos"})  # end-of-stream sentinel

    job.task = asyncio.create_task(worker())
    return {"job_id": job_id}


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


@app.get("/api/stream/{job_id}")
async def stream(job_id: str) -> StreamingResponse:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")

    async def gen():
        try:
            while True:
                event = await job.queue.get()
                if event.get("type") == "_eos":
                    yield "event: end\ndata: {}\n\n"
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            _JOBS.pop(job_id, None)
            if job.task and not job.task.done():
                job.task.cancel()
                with contextlib.suppress(Exception):
                    await job.task

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
