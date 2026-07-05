"""Base engine contract + a safe async subprocess runner."""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from typing import Awaitable, Callable

from ..schema import Finding, InputKind

# callback the orchestrator passes in so engines can stream findings live
Emit = Callable[[Finding], Awaitable[None]]


# project-local bin/ dir (holds standalone binaries like gosearch.exe, phoneinfoga.exe)
_PROJECT_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "bin")


def resolve_binary(name: str) -> str | None:
    """Find a CLI on PATH, next to the interpreter (venv Scripts/bin), or in ./bin.

    pip-installed console scripts land in the venv's Scripts/ (Windows) or bin/
    dir, which is NOT on PATH unless the venv is activated. Standalone Go binaries
    we ship live in the project's bin/. We call python via its full path, so look
    in all three places.
    """
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

    async def run(self, target: str, kind: InputKind, emit: Emit) -> list[Finding]:
        raise NotImplementedError


async def run_cmd(
    cmd: list[str], cwd: str | None = None, timeout: int = 240
) -> tuple[int, str, str]:
    """Run a command, never raise on failure. Returns (rc, stdout, stderr)."""
    # Force UTF-8 in the child. Several engines (maigret) print Unicode banners
    # that crash on a Windows cp1252 console before doing any real work.
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
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", "timeout"
    return (
        proc.returncode if proc.returncode is not None else 1,
        out.decode(errors="ignore"),
        err.decode(errors="ignore"),
    )
