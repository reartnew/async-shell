"""Shell evaluation tests"""
from __future__ import annotations

import os
import typing as t

import pytest

from async_shell import Shell, ShellResult

TEST_COMMAND: str = "echo a && echo b"


@pytest.mark.asyncio
async def test_async_subprocess_call() -> None:
    """Test simple call"""
    os_result = await Shell(TEST_COMMAND)
    assert not os_result.code


@pytest.mark.asyncio
@pytest.mark.parametrize("strip_linesep", [True, False], ids=["with-strip", "without-strip"])
async def test_stream_reader(strip_linesep: bool) -> None:
    """Validate stdout reader"""
    lines: t.List[str] = []
    async for line in Shell(TEST_COMMAND).read_stdout(strip_linesep=strip_linesep):
        assert line.endswith(os.linesep) != strip_linesep
        lines.append(line.rstrip())
    clean_result: ShellResult = await Shell(TEST_COMMAND).validate()
    assert lines == clean_result.stdout.splitlines()
