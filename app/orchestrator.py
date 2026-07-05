"""Fan input to the right engines, stream findings, pivot, dedup."""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from .dispatcher import (
    detect,
    username_candidates_from_name,
    username_from_email,
)
from .engines import ALL_ENGINES
from .schema import Finding, InputKind
from .siteinfo import describe

# event pushed to the live stream: {"type": ..., ...}
Event = dict
EventSink = Callable[[Event], Awaitable[None]]


async def orchestrate(query: str, kind: InputKind | None, pivot: bool, sink: EventSink) -> list[Finding]:
    kind = kind or detect(query)
    await sink({"type": "detected", "query": query, "kind": kind.value})

    seen: set[tuple] = set()
    results: list[Finding] = []

    async def emit(f: Finding) -> None:
        k = f.key()
        if k in seen:
            return
        seen.add(k)
        # enrich: give account findings a 'what is this site' blurb if they have none
        if f.kind == "account" and "about" not in f.extra:
            desc = describe(f.site, f.url)
            if desc:
                f.extra["about"] = desc
        results.append(f)
        await sink({"type": "finding", "finding": f.model_dump()})

    # ---- wave 1: run engines that accept the raw input kind ----
    await _run_wave(query, kind, emit, sink)

    # ---- wave 2: pivot — derive usernames and re-run username engines ----
    if pivot:
        pivots: list[str] = []
        if kind is InputKind.email:
            pivots = [username_from_email(query)]
        elif kind is InputKind.name:
            pivots = username_candidates_from_name(query)[:2]  # bound the blowup
        for handle in pivots:
            if not handle or handle == query:
                continue
            await sink({"type": "pivot", "handle": handle})
            await _run_wave(handle, InputKind.username, emit, sink)

    await sink({"type": "done", "count": len(results)})
    return results


async def _run_wave(target: str, kind: InputKind, emit, sink: EventSink) -> None:
    engines = [e for e in ALL_ENGINES if e.handles(kind)]
    tasks = []
    for e in engines:
        if not e.available():
            await sink({"type": "engine_skip", "engine": e.name, "reason": "not installed"})
            continue
        tasks.append(_run_engine(e, target, kind, emit, sink))
    if tasks:
        await asyncio.gather(*tasks)


async def _run_engine(engine, target, kind, emit, sink: EventSink) -> None:
    await sink({"type": "engine_start", "engine": engine.name, "target": target})
    try:
        found = await engine.run(target, kind, emit)
        await sink({"type": "engine_done", "engine": engine.name, "count": len(found)})
    except Exception as e:  # engine must never take the whole run down
        await sink({"type": "engine_error", "engine": engine.name, "error": str(e)})
