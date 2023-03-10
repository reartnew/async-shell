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

ST = t.TypeVar("ST", bound="Shell")

__all__ = [
    "ShellResult",
    "ShellError",
    "Shell",
]


class ShellError(Exception):
    """Subprocess non-zero exit code failure on .validate() call"""

    _prefix: str = "    "

    def __init__(self, result: ShellResult) -> None:
        msg: str = f"Subprocess failed with code: {result.code}\n"
        if result.stdout:
            msg += f"{self._prefix}PROCESS STDOUT:\n{textwrap.indent(result.stdout, self._prefix * 2)}\n"
        if result.stderr:
            msg += f"{self._prefix}PROCESS STDERR:\n{textwrap.indent(result.stderr, self._prefix * 2)}\n"
        super().__init__(msg)


@dataclass
class ShellResult:
    """Subprocess result container"""

    stdout: str
    stderr: str
    code: int
    time: float

    def __bool__(self) -> bool:
        return bool(self.code)

    def validate(self) -> ShellResult:
        """Raise SubprocessError on failure"""
        if self.code:
            raise ShellError(self)
        return self


class Shell(t.Awaitable[ShellResult]):
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
        self._post_validate: bool = False

    def validate(self) -> Shell:
        """Mark shell subprocess as requiring validation after evaluation"""
        self._post_validate = True
        return self

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

    async def _await(self) -> ShellResult:
        proc: Process = await self._get_proc()  # type: ignore
        stdout_bytes, stderr_bytes = await proc.communicate()
        result = ShellResult(
            stdout=stdout_bytes.decode(self._encoding),
            stderr=stderr_bytes.decode(self._encoding),
            code=proc.returncode,  # type: ignore
            time=time.perf_counter() - self._start_time,  # type: ignore
        )
        if self._post_validate:
            result.validate()
        return result

    def __await__(self):
        # pylint: disable=no-member
        return self._await().__await__()

    def __or__(self, other: Shell) -> Shell:
        if self._encoding != other._encoding:
            raise ValueError(f"Encoding mismatch: {self._encoding!r} != {other._encoding!r}")
        if self._start_time is not None:
            raise RuntimeError(f"Process {self} has already been started")
        if other._start_time is not None:
            raise RuntimeError(f"Process {other} has already been started")
        result = Shell(command=f"{self._command} | {other._command}", encoding=self._encoding)
        if self._post_validate or other._post_validate:
            result.validate()
        return result

    async def __aenter__(self: ST) -> ST:
        await self._get_proc()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        # TODO: graceful finish
        return exc_type is None
