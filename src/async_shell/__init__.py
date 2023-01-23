"""Asyncio subprocess shell command wrapper"""
from __future__ import annotations

import os
import textwrap
import time
import typing as t
from asyncio.streams import StreamReader
from asyncio.subprocess import create_subprocess_shell, Process  # noqa
from dataclasses import dataclass
from subprocess import PIPE

from .version import __version__

AST = t.TypeVar("AST", bound="AsyncSubprocessShell")

__all__ = [
    "AsyncSubprocessShellResult",
    "AsyncSubprocessShellError",
    "AsyncSubprocessShell",
]


class AsyncSubprocessShellError(Exception):
    """Subprocess non-zero exit code failure on .validate() call"""

    _prefix: str = "    "

    def __init__(self, result: AsyncSubprocessShellResult) -> None:
        msg: str = f"Subprocess failed with code: {result.code}\n"
        if result.stdout:
            msg += f"{self._prefix}PROCESS STDOUT:\n{textwrap.indent(result.stdout, self._prefix * 2)}\n"
        if result.stderr:
            msg += f"{self._prefix}PROCESS STDERR:\n{textwrap.indent(result.stderr, self._prefix * 2)}\n"
        super().__init__(msg)


@dataclass
class AsyncSubprocessShellResult:
    """Subprocess result container"""

    stdout: str
    stderr: str
    code: int
    time: float

    def __bool__(self) -> bool:
        return bool(self.code)

    def validate(self) -> AsyncSubprocessShellResult:
        """Raise SubprocessError on failure"""
        if self.code:
            raise AsyncSubprocessShellError(self)
        return self


class AsyncSubprocessShell:
    """Asyncio subprocess wrapper"""

    def __init__(
        self,
        command: str,
        encoding: t.Optional[str] = None,
    ) -> None:
        self._command: str = command
        self._proc: t.Optional[Process] = None
        self._encoding: str = encoding or ("cp866" if os.name == "nt" else "utf-8")
        self._start_time: t.Optional[float] = None

    async def _get_proc(self) -> Process:
        if self._proc is None:
            self._start_time = time.perf_counter()
            self._proc = await create_subprocess_shell(
                cmd=self._command,
                stdin=None,
                stdout=PIPE,
                stderr=PIPE,
            )
        return self._proc

    async def read_stdout(self) -> t.AsyncGenerator[str, None]:
        """Run through stdout data and yield decoded strings line by line"""
        proc: Process = await self._get_proc()
        stdout: StreamReader = proc.stdout  # type: ignore
        async for chunk in stdout:  # type: bytes
            yield chunk.decode(self._encoding)

    async def read_stderr(self) -> t.AsyncGenerator[str, None]:
        """Same as .read_stdout(), but for stderr"""
        proc: Process = await self._get_proc()
        stderr: StreamReader = proc.stderr  # type: ignore
        async for chunk in stderr:  # type: bytes
            yield chunk.decode(self._encoding)

    async def _await(self):
        proc: Process = await self._get_proc()  # type: ignore
        stdout_bytes, stderr_bytes = await proc.communicate()
        return AsyncSubprocessShellResult(
            stdout=stdout_bytes.decode(self._encoding),
            stderr=stderr_bytes.decode(self._encoding),
            code=proc.returncode,
            time=time.perf_counter() - self._start_time,
        )

    def __await__(self):
        # pylint: disable=no-member
        return self._await().__await__()

    async def __aenter__(self: AST) -> AST:
        await self._get_proc()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        return exc_type is None
