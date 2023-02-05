"""OS-related constants"""

import sys
import os

__all__ = [
    "IS_MACOS",
    "IS_WIN32",
]

IS_WIN32: bool = os.name == "nt"
IS_MACOS: bool = sys.platform == "darwin"
