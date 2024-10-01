"""Shell evaluation tests"""

from __future__ import annotations

import os
import typing as t

import pytest

from async_shell import (
    Shell,
    ShellResult,
    constants,
    check_output,
    ShellError,
)

TEST_ECHO_COMMAND: str = "echo a && echo b"


@pytest.mark.asyncio
async def test_async_subprocess_call() -> None:
    """Test simple call"""
    process = Shell(TEST_ECHO_COMMAND)
    os_result = await process
    assert not os_result.code
    assert not process.was_stopped


@pytest.mark.asyncio
async def test_finalizer() -> None:
    """Test process premature finalizer"""
    process = Shell("sleep 10000")
    async with process:
        assert process.pid > 0
    assert process.was_stopped


@pytest.mark.asyncio
async def test_env() -> None:
    """Test process environment passing"""
    async with Shell(
        command="echo %ASYNC_SHELL_TEST_VAR%" if constants.IS_WIN32 else "echo $ASYNC_SHELL_TEST_VAR",
        environment={"ASYNC_SHELL_TEST_VAR": "Foo"},
    ) as process:
        result = await process.validate()
        assert result.stdout == "Foo\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("strip_linesep", [True, False], ids=["with-strip", "without-strip"])
async def test_stream_reader(strip_linesep: bool) -> None:
    """Validate stdout reader"""
    lines: t.List[str] = []
    async for line in Shell(TEST_ECHO_COMMAND).read_stdout(strip_linesep=strip_linesep):
        assert line.endswith(os.linesep) != strip_linesep
        lines.append(line.rstrip())
    clean_result: ShellResult = await Shell(TEST_ECHO_COMMAND).validate()
    assert lines == clean_result.stdout.splitlines()


@pytest.mark.asyncio
async def test_check_output_ok() -> None:
    """Test check_output function good call"""
    assert await check_output(TEST_ECHO_COMMAND) == "a\nb\n"


@pytest.mark.asyncio
async def test_check_output_fail() -> None:
    """Test check_output function bad call"""
    with pytest.raises(ShellError, match="foobar: command not found"):
        assert await check_output("foobar")


@pytest.mark.asyncio
@pytest.mark.parametrize("executable", [None, "/bin/sh", "/bin/bash"])
async def test_specific_shells(executable: str) -> None:
    """Test specifying a shell executable"""
    await check_output("echo foo", executable=executable)
