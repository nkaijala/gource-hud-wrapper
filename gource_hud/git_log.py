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


_RENAME_BRACE_RE = re.compile(r"\{([^}]*) => ([^}]*)\}")


def _resolve_numstat_path(raw_path: str) -> str:
    m = _RENAME_BRACE_RE.search(raw_path)
    if m:
        result = raw_path[: m.start()] + m.group(2) + raw_path[m.end():]
        return result.lstrip("/")
    if " => " in raw_path:
        return raw_path.split(" => ", 1)[1]
    return raw_path


@dataclass
class _NumstatCommit:
    timestamp: int
    hash: str
    author_email: str
    file_stats: list[tuple[int, int, str, bool]] = field(default_factory=list)


def _is_hex(s: str) -> bool:
    return len(s) in (40, 64) and all(c in string.hexdigits for c in s)


def _parse_numstat_output(raw: str) -> list[_NumstatCommit]:
    results: list[_NumstatCommit] = []
    current: _NumstatCommit | None = None
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and _is_hex(parts[1]):
            if current is not None:
                results.append(current)
            current = _NumstatCommit(timestamp=int(parts[0]), hash=parts[1], author_email=parts[2])
            continue
        if current is not None and len(parts) >= 3:
            adds_s, dels_s = parts[0], parts[1]
            path = "\t".join(parts[2:])
            path = _resolve_numstat_path(path)
            if adds_s == "-" and dels_s == "-":
                current.file_stats.append((0, 0, path, True))
            else:
                try:
                    current.file_stats.append((int(adds_s), int(dels_s), path, False))
                except ValueError:
                    continue
    if current is not None:
        results.append(current)
    return results


@dataclass
class _NameStatusEntry:
    status: FileStatus
    path: str
    old_path: Optional[str] = None
    score: Optional[int] = None


@dataclass
class _NameStatusCommit:
    timestamp: int
    hash: str
    entries: list[_NameStatusEntry] = field(default_factory=list)


def _parse_name_status_output(raw: str) -> list[_NameStatusCommit]:
    results: list[_NameStatusCommit] = []
    current: _NameStatusCommit | None = None
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 2 and parts[0].isdigit() and _is_hex(parts[1]):
            if current is not None:
                results.append(current)
            current = _NameStatusCommit(timestamp=int(parts[0]), hash=parts[1])
            continue
        if current is not None and len(parts) >= 2:
            status_code = parts[0]
            if status_code in ("A", "M", "D", "T"):
                current.entries.append(_NameStatusEntry(status=FileStatus(status_code), path=parts[1]))
            elif status_code.startswith(("R", "C")):
                letter = status_code[0]
                try:
                    score = int(status_code[1:]) if len(status_code) > 1 else 100
                except ValueError:
                    score = 100
                fs = FileStatus.RENAMED if letter == "R" else FileStatus.COPIED
                old_path = parts[1]
                new_path = parts[2] if len(parts) >= 3 else parts[1]
                current.entries.append(_NameStatusEntry(status=fs, path=new_path, old_path=old_path, score=score))
    if current is not None:
        results.append(current)
    return results


def _merge_commits(numstat_commits: list[_NumstatCommit], name_status_commits: list[_NameStatusCommit]) -> list[Commit]:
    ns_by_hash = {c.hash: c for c in numstat_commits}
    st_by_hash = {c.hash: c for c in name_status_commits}
    all_hashes = set(ns_by_hash) | set(st_by_hash)
    result: list[Commit] = []
    for h in all_hashes:
        ns = ns_by_hash.get(h)
        st = st_by_hash.get(h)
        timestamp = ns.timestamp if ns else st.timestamp
        author = ns.author_email if ns else ""
        commit = Commit(timestamp=timestamp, hash=h, author_email=author)
        status_lookup: dict[str, _NameStatusEntry] = {}
        if st:
            for entry in st.entries:
                status_lookup[entry.path] = entry
        seen_paths: set[str] = set()
        if ns:
            for adds, deletes, path, is_binary in ns.file_stats:
                seen_paths.add(path)
                entry = status_lookup.get(path)
                commit.files.append(FileChange(
                    path=path, status=entry.status if entry else FileStatus.MODIFIED,
                    adds=adds, deletes=deletes, is_binary=is_binary,
                    old_path=entry.old_path if entry else None,
                    rename_score=entry.score if entry else None,
                ))
        if st:
            for entry in st.entries:
                if entry.path not in seen_paths:
                    commit.files.append(FileChange(
                        path=entry.path, status=entry.status, adds=0, deletes=0,
                        is_binary=False, old_path=entry.old_path, rename_score=entry.score,
                    ))
        result.append(commit)
    result.sort(key=lambda c: (c.timestamp, c.hash))
    return result


class Anonymizer:
    def __init__(self) -> None:
        self._author_map: dict[str, str] = {}
        self._author_counter = 0
        self._dir_map: dict[str, str] = {}
        self._dir_counter = 0
        self._file_map: dict[str, str] = {}
        self._file_counter = 0

    def anonymize_author(self, email: str) -> str:
        if email not in self._author_map:
            self._author_counter += 1
            self._author_map[email] = f"Dev_{self._author_counter}"
        return self._author_map[email]

    def anonymize_path(self, path: str) -> str:
        parts = path.split("/")
        anon_parts: list[str] = []
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            if is_last:
                dot_idx = part.rfind(".")
                if dot_idx > 0:
                    base = part[:dot_idx]
                    ext = part[dot_idx:]
                else:
                    base = part
                    ext = ""
                if base not in self._file_map:
                    self._file_counter += 1
                    self._file_map[base] = f"f{self._file_counter:04d}"
                anon_parts.append(self._file_map[base] + ext)
            else:
                if part not in self._dir_map:
                    self._dir_counter += 1
                    self._dir_map[part] = f"d{self._dir_counter:04d}"
                anon_parts.append(self._dir_map[part])
        return "/".join(anon_parts)

    def anonymize_commits(self, commits: list[Commit]) -> list[Commit]:
        result: list[Commit] = []
        for c in commits:
            anon_author = self.anonymize_author(c.author_email)
            anon_files: list[FileChange] = []
            for f in c.files:
                anon_files.append(FileChange(
                    path=self.anonymize_path(f.path), status=f.status,
                    adds=f.adds, deletes=f.deletes, is_binary=f.is_binary,
                    old_path=self.anonymize_path(f.old_path) if f.old_path else None,
                    rename_score=f.rename_score,
                ))
            result.append(Commit(timestamp=c.timestamp, hash=c.hash, author_email=anon_author, files=anon_files))
        return result
