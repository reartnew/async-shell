"""Shell evaluation tests"""
from __future__ import annotations

import os
from typing import TypedDict

import pytest
from pytest_data_suites import DataSuite

from async_shell import Shell
from async_shell.constants import IS_MACOS, IS_WIN32


class ShellCase(TypedDict):
    """Execution case template"""

    executable: str
    command: str


class WindowsShellDataSuite(DataSuite):
    """Windows cases"""

    win_cmd = ShellCase(executable="cmd", command="dir")
    win_powershell = ShellCase(executable="powershell", command="dir")


class MacOSShellDataSuite(DataSuite):
    """MacOS cases"""

    # Use script for tty
    mac_os_sh = ShellCase(executable="script -q /dev/null sh --rcfile <(echo PS1='$')", command="ls -la")
    mac_os_bash = ShellCase(executable="script -q /dev/null bash --rcfile <(echo PS1='$')", command="ls -la")


class LinuxShellDataSuite(DataSuite):
    """Linux cases"""

    # Use script for tty
    linux_sh = ShellCase(executable="script -qc sh /dev/null", command="pwd")
    linux_bash = ShellCase(executable="script -qc bash /dev/null", command="pwd")


ShellDataSuite = WindowsShellDataSuite if IS_WIN32 else MacOSShellDataSuite if IS_MACOS else LinuxShellDataSuite


@ShellDataSuite.parametrize
@pytest.mark.asyncio
async def test_async_subprocess_call(command: str) -> None:
    """Test simple call"""
    os_result = await Shell(command)
    assert not os_result.code


@ShellDataSuite.parametrize
@pytest.mark.asyncio
@pytest.mark.parametrize("strip_linesep", [True, False], ids=["with-strip", "without-strip"])
async def test_stream_reader(command: str, strip_linesep: bool) -> None:
    """Validate stdout reader"""
    async for line in Shell(command).read_stdout(strip_linesep=strip_linesep):
        assert line.endswith(os.linesep) != strip_linesep
