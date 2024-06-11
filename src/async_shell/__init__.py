"""Asyncio subprocess shell command wrapper"""

from __future__ import annotations

import os
import textwrap
import time
import typing as t
from asyncio.streams import StreamReader
from asyncio.subprocess import create_subprocess_shell, Process  # noqa
from dataclasses import dataclass
from subprocess import PIPE  # nosec

from classlogging import LoggerMixin

from .constants import IS_WIN32
from .version import __version__

ST = t.TypeVar("ST", bound="Shell")

__all__ = [
    "ShellResult",
    "ShellError",
    "Shell",
    "check_output",
]


class ShellError(Exception):
    """Subprocess non-zero exit code failure on .validate() call"""

    _prefix: str = "    "

    def __init__(self, result: ShellResult) -> None:
        msg: str = f"Subprocess failed with code: {result.code}"
        if result.stdout:
            msg += f"\n{self._prefix}PROCESS STDOUT:\n{textwrap.indent(result.stdout, self._prefix * 2)}"
        if result.stderr:
            msg += f"\n{self._prefix}PROCESS STDERR:\n{textwrap.indent(result.stderr, self._prefix * 2)}"
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


class Shell(t.Awaitable[ShellResult], LoggerMixin):
    """Asyncio subprocess wrapper"""

    _DEFAULT_ENCODING: str = "cp866" if IS_WIN32 else "utf-8"
    _BYTES_LINESEP: bytes = os.linesep.encode()
    MISSING_PROCESS_PID: int = -1

    def __init__(
        self,
        command: str,
        encoding: t.Optional[str] = None,
        environment: t.Optional[t.Dict[str, str]] = None,
        cwd: t.Optional[str] = None,
    ) -> None:
        self._command: str = command
        self._proc: t.Optional[Process] = None
        self._encoding: str = encoding or self._DEFAULT_ENCODING
        self._start_time: t.Optional[float] = None
        self._post_validate: bool = False
        self._was_stopped: bool = False
        self._was_finalized: bool = False
        self._env: t.Optional[t.Dict[str, str]] = environment
        self._cwd: t.Optional[str] = cwd

    @property
    def was_stopped(self) -> bool:
        """Tell if the process was stopped during execution"""
        return self._was_stopped

    @property
    def pid(self) -> int:
        """Return underlying process PID, if any, or MISSING_PROCESS_PID otherwise"""
        return self.MISSING_PROCESS_PID if self._proc is None else self._proc.pid

    def validate(self) -> Shell:
        """Mark shell subprocess as requiring validation after evaluation"""
        self._post_validate = True
        return self

    async def _get_proc(self) -> Process:
        if self._proc is None:
            self._start_time = time.perf_counter()
            self.logger.trace(f"Starting subprocess: {self._command!r}")
            self._proc = await create_subprocess_shell(
                cmd=self._command,
                stdin=None,
                stdout=PIPE,
                stderr=PIPE,
                env=self._env,
                cwd=self._cwd,
            )
            self.logger.debug(f"Started process with PID {self.pid}")
        return self._proc

    async def read_stdout(self, strip_linesep: bool = True) -> t.AsyncGenerator[str, None]:
        """Run through stdout data and yield decoded strings line by line"""
        proc: Process = await self._get_proc()
        stdout: StreamReader = proc.stdout  # type: ignore
        async for chunk in stdout:  # type: bytes
            if strip_linesep:
                chunk = chunk.rstrip(self._BYTES_LINESEP)
            yield chunk.decode(self._encoding)

    async def read_stderr(self, strip_linesep: bool = True) -> t.AsyncGenerator[str, None]:
        """Same as .read_stdout(), but for stderr"""
        proc: Process = await self._get_proc()
        stderr: StreamReader = proc.stderr  # type: ignore
        async for chunk in stderr:  # type: bytes
            if strip_linesep:
                chunk = chunk.rstrip(self._BYTES_LINESEP)
            yield chunk.decode(self._encoding)

    async def _await(self) -> ShellResult:
        try:
            return await self._run()
        finally:
            await self._finalize()

    async def _run(self) -> ShellResult:
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

    async def __aenter__(self: ST) -> ST:
        await self._get_proc()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self._finalize()
        return exc_type is None

    def poll(self) -> bool:
        """Check if the subprocess has finished"""
        return self._proc is not None and self._proc.returncode is not None

    async def _finalize(self) -> None:
        if self._was_finalized:
            return
        if self._proc is None:
            self.logger.warning("Finalizing non-started process")
            return
        self.logger.debug(f"Finalizing process with PID {self.pid}")
        if self._proc.returncode is None:
            self.logger.trace(f"Killing process with PID {self.pid}")
            self._proc.kill()
            self._was_stopped = True
        # Close communication anyway
        await self._proc.communicate()
        for stream in (self._proc.stdout, self._proc.stderr, self._proc.stdin):
            if stream is None:
                continue
            self.logger.trace(f"Closing stream: {stream}")
            stream._transport.close()  # type: ignore[union-attr]  # pylint: disable=protected-access
        self._was_finalized = True


async def check_output(
    command: str,
    encoding: t.Optional[str] = None,
    environment: t.Optional[t.Dict[str, str]] = None,
    cwd: t.Optional[str] = None,
) -> str:
    """Run shell with arguments and return its output.
    If the exit code was non-zero it raises a ShellError.
    The arguments are the same as for the Shell constructor."""
    async with Shell(
        command=command,
        encoding=encoding,
        environment=environment,
        cwd=cwd,
    ) as process:
        result = await process.validate()
    return result.stdout
