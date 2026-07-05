"""Base engine contract + a safe, streaming async subprocess runner."""
from __future__ import annotations

import asyncio
import contextvars
import os
import shutil
import sys
from typing import Awaitable, Callable

from ..schema import Finding, InputKind

# per-request job id (set by the API worker) so we can track & kill a job's
# subprocesses directly, without relying on slow Proactor cancellation.
current_job: contextvars.ContextVar = contextvars.ContextVar("current_job", default=None)
# per-request deep-scan override (True/False), or None to use the engine default.
deep_scan: contextvars.ContextVar = contextvars.ContextVar("deep_scan", default=None)
_LIVE_PROCS: dict = {}   # job_id -> set of live Process objects


def _register(proc):
    jid = current_job.get()
    if jid is not None:
        _LIVE_PROCS.setdefault(jid, set()).add(proc)
    return jid


def _unregister(jid, proc):
    s = _LIVE_PROCS.get(jid)
    if s:
        s.discard(proc)
        if not s:
            _LIVE_PROCS.pop(jid, None)


def kill_job(job_id) -> int:
    """Immediately kill every subprocess (and its tree) belonging to a job."""
    procs = list(_LIVE_PROCS.get(job_id, set()))
    for p in procs:
        _kill(p)
    return len(procs)

# callbacks the orchestrator passes in
Emit = Callable[[Finding], Awaitable[None]]        # stream a finding live
Progress = Callable[[dict], Awaitable[None]]       # stream a progress update
OnLine = Callable[[str], Awaitable[None]]          # per-line stdout handler


# project-local bin/ dir (holds standalone binaries like gosearch.exe, phoneinfoga.exe)
_PROJECT_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "bin")


def resolve_binary(name: str) -> str | None:
    """Find a CLI on PATH, next to the interpreter (venv Scripts/bin), or in ./bin."""
    if not name:
        return None
    hit = shutil.which(name)
    if hit:
        return hit
    for folder in (os.path.dirname(sys.executable), _PROJECT_BIN):
        for cand in (name, name + ".exe"):
            p = os.path.join(folder, cand)
            if os.path.isfile(p):
                return p
    return None


async def _noprog(_evt: dict) -> None:
    return None


class Engine:
    name: str = "base"
    binary: str = ""                       # CLI executable to look for
    accepts: tuple[InputKind, ...] = ()     # which input kinds this engine handles

    def exe(self) -> str | None:
        return resolve_binary(self.binary)

    def available(self) -> bool:
        return self.exe() is not None

    def handles(self, kind: InputKind) -> bool:
        return kind in self.accepts

    async def run(self, target: str, kind: InputKind, emit: Emit,
                  progress: Progress = _noprog) -> list[Finding]:
        raise NotImplementedError


async def run_cmd(
    cmd: list[str], cwd: str | None = None, timeout: int = 240,
    on_line: OnLine | None = None,
) -> tuple[int, str, str]:
    """Run a command, streaming stdout line-by-line to on_line as it arrives.

    Never raises on process failure (returns rc/out/err). On task cancellation
    (user pressed Stop) the child process is killed and CancelledError re-raised.
    """
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
    except (FileNotFoundError, OSError) as e:
        return 127, "", f"spawn failed: {e}"

    jid = _register(proc)
    out_parts: list[str] = []
    err_parts: list[str] = []

    async def pump(stream, parts, feed_line):
        while True:
            raw = await stream.readline()
            if not raw:
                break
            s = raw.decode(errors="ignore")
            parts.append(s)
            if feed_line and on_line:
                try:
                    await on_line(s)
                except Exception:
                    pass  # a bad parse must never kill the scan

    try:
        await asyncio.wait_for(
            asyncio.gather(pump(proc.stdout, out_parts, True),
                           pump(proc.stderr, err_parts, False)),
            timeout=timeout,
        )
        await proc.wait()
    except asyncio.TimeoutError:
        _kill(proc)
        return 124, "".join(out_parts), "timeout"
    except asyncio.CancelledError:
        _kill(proc)
        raise
    finally:
        if proc.returncode is None:
            _kill(proc)
        _unregister(jid, proc)
    return proc.returncode if proc.returncode is not None else 1, "".join(out_parts), "".join(err_parts)


def _kill(proc) -> None:
    """Kill the child AND all descendants (children first).

    A pip console-script (maigret.exe/sherlock.exe) is only a launcher that
    spawns a separate python.exe; killing the launcher alone orphans that
    grandchild. psutil walks the real process tree; taskkill /T is the fallback.
    """
    try:
        import psutil
        try:
            parent = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            return
        victims = parent.children(recursive=True) + [parent]
        for p in victims:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(victims, timeout=3)
        return
    except Exception:
        pass
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, check=False)
        else:
            proc.kill()
    except (ProcessLookupError, OSError):
        pass
