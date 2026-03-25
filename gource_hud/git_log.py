from __future__ import annotations
import re
import string
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class FileStatus(Enum):
    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    TYPE_CHANGED = "T"
    RENAMED = "R"
    COPIED = "C"


@dataclass
class FileChange:
    path: str
    status: FileStatus
    adds: int
    deletes: int
    is_binary: bool
    old_path: Optional[str] = None
    rename_score: Optional[int] = None


@dataclass
class Commit:
    timestamp: int
    hash: str
    author_email: str
    files: list[FileChange] = field(default_factory=list)

    @property
    def day_epoch(self) -> int:
        return (self.timestamp // 86400) * 86400
