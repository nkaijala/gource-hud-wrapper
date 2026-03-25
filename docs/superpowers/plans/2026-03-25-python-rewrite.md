# Gource HUD Wrapper Python Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite gource_anon_hud.sh as a pip-installable pure Python package with full test coverage.

**Architecture:** In-process pipeline — git log parsed natively, stats computed as pure data structures, Pillow renders overlays, gource+ffmpeg orchestrated via subprocess. Five modules: git_log, stats, overlay, video, cli.

**Tech Stack:** Python 3.10+, Pillow, pytest, gource (system), ffmpeg (system)

**Spec:** `docs/superpowers/specs/2026-03-25-python-rewrite-design.md`

---

## Chunk 1: Project Scaffolding + git_log.py

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `gource_hud/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "gource-hud"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["pillow"]

[project.optional-dependencies]
dev = ["pytest"]

[project.scripts]
gource-hud = "gource_hud.cli:main"
```

- [ ] **Step 2: Create package init**

```python
# gource_hud/__init__.py
```

(Empty file.)

- [ ] **Step 3: Create tests init**

```python
# tests/__init__.py
```

(Empty file.)

- [ ] **Step 4: Install in editable mode and verify**

Run: `pip install -e ".[dev]"`
Expected: Successfully installed gource-hud-0.1.0 (and pillow, pytest)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml gource_hud/__init__.py tests/__init__.py
git commit -m "scaffold: add pyproject.toml and package structure"
```

---

### Task 2: Data structures for git_log.py

**Files:**
- Create: `gource_hud/git_log.py`
- Create: `tests/test_git_log.py`

- [ ] **Step 1: Write test for data structures**

```python
# tests/test_git_log.py
from gource_hud.git_log import FileStatus, FileChange, Commit


def test_file_status_values():
    assert FileStatus.ADDED.value == "A"
    assert FileStatus.MODIFIED.value == "M"
    assert FileStatus.DELETED.value == "D"
    assert FileStatus.TYPE_CHANGED.value == "T"
    assert FileStatus.RENAMED.value == "R"
    assert FileStatus.COPIED.value == "C"


def test_commit_day_epoch():
    c = Commit(
        timestamp=1700000000,
        hash="a" * 40,
        author_email="dev@example.com",
        files=[],
    )
    expected_day = (1700000000 // 86400) * 86400
    assert c.day_epoch == expected_day


def test_file_change_defaults():
    fc = FileChange(
        path="src/main.py",
        status=FileStatus.MODIFIED,
        adds=10,
        deletes=3,
        is_binary=False,
    )
    assert fc.old_path is None
    assert fc.rename_score is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_git_log.py -v`
Expected: FAIL — cannot import `FileStatus`, `FileChange`, `Commit`

- [ ] **Step 3: Implement data structures**

```python
# gource_hud/git_log.py
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_git_log.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add gource_hud/git_log.py tests/test_git_log.py
git commit -m "feat(git_log): add data structures — FileStatus, FileChange, Commit"
```

---

### Task 3: Numstat parser

**Files:**
- Modify: `gource_hud/git_log.py`
- Modify: `tests/test_git_log.py`

- [ ] **Step 1: Write tests for numstat parsing**

Append to `tests/test_git_log.py`:

```python
from gource_hud.git_log import _parse_numstat_output, _resolve_numstat_path


class TestResolveNumstatPath:
    def test_simple_path(self):
        assert _resolve_numstat_path("src/main.py") == "src/main.py"

    def test_brace_rename(self):
        assert _resolve_numstat_path("src/{old => new}/file.py") == "src/new/file.py"

    def test_brace_rename_root(self):
        assert _resolve_numstat_path("{old.txt => new.txt}") == "new.txt"

    def test_simple_rename(self):
        assert _resolve_numstat_path("old.txt => new.txt") == "new.txt"

    def test_brace_empty_old(self):
        # File moved into a directory: { => subdir}/file.py
        assert _resolve_numstat_path("{ => subdir}/file.py") == "subdir/file.py"

    def test_brace_empty_new(self):
        # File moved out of a directory: leading slash stripped
        assert _resolve_numstat_path("{subdir => }/file.py") == "file.py"


class TestParseNumstatOutput:
    def test_single_commit_two_files(self):
        raw = (
            "1700000000\t" + "a" * 40 + "\tdev@example.com\n"
            "\n"
            "10\t3\tsrc/main.py\n"
            "5\t0\tsrc/utils.py\n"
        )
        commits = _parse_numstat_output(raw)
        assert len(commits) == 1
        c = commits[0]
        assert c.timestamp == 1700000000
        assert c.hash == "a" * 40
        assert c.author_email == "dev@example.com"
        assert len(c.file_stats) == 2
        assert c.file_stats[0] == (10, 3, "src/main.py", False)
        assert c.file_stats[1] == (5, 0, "src/utils.py", False)

    def test_binary_file(self):
        raw = (
            "1700000000\t" + "b" * 40 + "\tdev@example.com\n"
            "\n"
            "-\t-\timage.png\n"
        )
        commits = _parse_numstat_output(raw)
        assert commits[0].file_stats[0] == (0, 0, "image.png", True)

    def test_multiple_commits(self):
        raw = (
            "1700000000\t" + "a" * 40 + "\talice@x.com\n"
            "\n"
            "1\t0\ta.py\n"
            "\n"
            "1700086400\t" + "b" * 40 + "\tbob@x.com\n"
            "\n"
            "2\t1\tb.py\n"
        )
        commits = _parse_numstat_output(raw)
        assert len(commits) == 2
        assert commits[0].author_email == "alice@x.com"
        assert commits[1].author_email == "bob@x.com"

    def test_empty_commit(self):
        raw = "1700000000\t" + "c" * 40 + "\tdev@x.com\n"
        commits = _parse_numstat_output(raw)
        assert len(commits) == 1
        assert commits[0].file_stats == []

    def test_empty_input(self):
        assert _parse_numstat_output("") == []

    def test_rename_in_numstat(self):
        raw = (
            "1700000000\t" + "d" * 40 + "\tdev@x.com\n"
            "\n"
            "0\t0\tsrc/{old => new}/file.py\n"
        )
        commits = _parse_numstat_output(raw)
        assert commits[0].file_stats[0][2] == "src/new/file.py"

    def test_path_with_spaces(self):
        raw = (
            "1700000000\t" + "e" * 40 + "\tdev@x.com\n"
            "\n"
            "3\t1\tsrc/my file.py\n"
        )
        commits = _parse_numstat_output(raw)
        assert commits[0].file_stats[0][2] == "src/my file.py"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git_log.py -v -k "Numstat or Resolve"`
Expected: FAIL — cannot import `_parse_numstat_output`, `_resolve_numstat_path`

- [ ] **Step 3: Implement numstat parser**

Add to `gource_hud/git_log.py`:

```python
import string

_RENAME_BRACE_RE = re.compile(r"\{([^}]*) => ([^}]*)\}")


def _resolve_numstat_path(raw_path: str) -> str:
    m = _RENAME_BRACE_RE.search(raw_path)
    if m:
        result = raw_path[: m.start()] + m.group(2) + raw_path[m.end() :]
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
            current = _NumstatCommit(
                timestamp=int(parts[0]),
                hash=parts[1],
                author_email=parts[2],
            )
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_git_log.py -v -k "Numstat or Resolve"`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/git_log.py tests/test_git_log.py
git commit -m "feat(git_log): add numstat parser with rename resolution"
```

---

### Task 4: Name-status parser

**Files:**
- Modify: `gource_hud/git_log.py`
- Modify: `tests/test_git_log.py`

- [ ] **Step 1: Write tests for name-status parsing**

Append to `tests/test_git_log.py`:

```python
from gource_hud.git_log import _parse_name_status_output, _NameStatusEntry


class TestParseNameStatusOutput:
    def test_basic_amd(self):
        raw = (
            "1700000000\t" + "a" * 40 + "\n"
            "\n"
            "A\tnew_file.py\n"
            "M\texisting.py\n"
            "D\told_file.py\n"
        )
        commits = _parse_name_status_output(raw)
        assert len(commits) == 1
        entries = commits[0].entries
        assert len(entries) == 3
        assert entries[0].status == FileStatus.ADDED
        assert entries[0].path == "new_file.py"
        assert entries[1].status == FileStatus.MODIFIED
        assert entries[2].status == FileStatus.DELETED

    def test_rename(self):
        raw = (
            "1700000000\t" + "a" * 40 + "\n"
            "\n"
            "R100\told.py\tnew.py\n"
        )
        commits = _parse_name_status_output(raw)
        entry = commits[0].entries[0]
        assert entry.status == FileStatus.RENAMED
        assert entry.path == "new.py"
        assert entry.old_path == "old.py"
        assert entry.score == 100

    def test_copy(self):
        raw = (
            "1700000000\t" + "a" * 40 + "\n"
            "\n"
            "C075\tsrc.py\tdst.py\n"
        )
        commits = _parse_name_status_output(raw)
        entry = commits[0].entries[0]
        assert entry.status == FileStatus.COPIED
        assert entry.score == 75

    def test_type_change(self):
        raw = (
            "1700000000\t" + "a" * 40 + "\n"
            "\n"
            "T\tsymlink.txt\n"
        )
        commits = _parse_name_status_output(raw)
        assert commits[0].entries[0].status == FileStatus.TYPE_CHANGED

    def test_empty_commit(self):
        raw = "1700000000\t" + "a" * 40 + "\n"
        commits = _parse_name_status_output(raw)
        assert len(commits) == 1
        assert commits[0].entries == []

    def test_empty_input(self):
        assert _parse_name_status_output("") == []

    def test_multiple_commits(self):
        raw = (
            "1700000000\t" + "a" * 40 + "\n"
            "\n"
            "A\ta.py\n"
            "\n"
            "1700086400\t" + "b" * 40 + "\n"
            "\n"
            "M\tb.py\n"
        )
        commits = _parse_name_status_output(raw)
        assert len(commits) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git_log.py::TestParseNameStatusOutput -v`
Expected: FAIL — cannot import `_parse_name_status_output`

- [ ] **Step 3: Implement name-status parser**

Add to `gource_hud/git_log.py`:

```python
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
            current = _NameStatusCommit(
                timestamp=int(parts[0]),
                hash=parts[1],
            )
            continue
        if current is not None and len(parts) >= 2:
            status_code = parts[0]
            if status_code in ("A", "M", "D", "T"):
                current.entries.append(
                    _NameStatusEntry(
                        status=FileStatus(status_code),
                        path=parts[1],
                    )
                )
            elif status_code.startswith(("R", "C")):
                letter = status_code[0]
                try:
                    score = int(status_code[1:]) if len(status_code) > 1 else 100
                except ValueError:
                    score = 100
                fs = FileStatus.RENAMED if letter == "R" else FileStatus.COPIED
                old_path = parts[1]
                new_path = parts[2] if len(parts) >= 3 else parts[1]
                current.entries.append(
                    _NameStatusEntry(
                        status=fs,
                        path=new_path,
                        old_path=old_path,
                        score=score,
                    )
                )

    if current is not None:
        results.append(current)
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_git_log.py::TestParseNameStatusOutput -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/git_log.py tests/test_git_log.py
git commit -m "feat(git_log): add name-status parser"
```

---

### Task 5: Commit merging

**Files:**
- Modify: `gource_hud/git_log.py`
- Modify: `tests/test_git_log.py`

- [ ] **Step 1: Write tests for merge logic**

Append to `tests/test_git_log.py`:

```python
from gource_hud.git_log import _merge_commits, _NumstatCommit, _NameStatusCommit, _NameStatusEntry


class TestMergeCommits:
    def test_basic_merge(self):
        ns = [_NumstatCommit(1700000000, "a" * 40, "dev@x.com",
              [(10, 3, "main.py", False)])]
        st = [_NameStatusCommit(1700000000, "a" * 40,
              [_NameStatusEntry(FileStatus.MODIFIED, "main.py")])]
        result = _merge_commits(ns, st)
        assert len(result) == 1
        assert result[0].files[0].status == FileStatus.MODIFIED
        assert result[0].files[0].adds == 10
        assert result[0].files[0].deletes == 3

    def test_file_only_in_name_status(self):
        """Permission-only change: appears in name-status but not numstat."""
        ns = [_NumstatCommit(1700000000, "a" * 40, "dev@x.com", [])]
        st = [_NameStatusCommit(1700000000, "a" * 40,
              [_NameStatusEntry(FileStatus.MODIFIED, "perms.sh")])]
        result = _merge_commits(ns, st)
        f = result[0].files[0]
        assert f.path == "perms.sh"
        assert f.adds == 0
        assert f.deletes == 0

    def test_commit_only_in_numstat(self):
        """Defensive: commit hash appears only in numstat."""
        ns = [_NumstatCommit(1700000000, "a" * 40, "dev@x.com",
              [(5, 2, "x.py", False)])]
        st: list[_NameStatusCommit] = []
        result = _merge_commits(ns, st)
        assert len(result) == 1
        assert result[0].files[0].status == FileStatus.MODIFIED  # default

    def test_output_sorted_by_timestamp(self):
        ns = [
            _NumstatCommit(1700086400, "b" * 40, "b@x.com", []),
            _NumstatCommit(1700000000, "a" * 40, "a@x.com", []),
        ]
        st: list[_NameStatusCommit] = []
        result = _merge_commits(ns, st)
        assert result[0].timestamp < result[1].timestamp

    def test_rename_merged(self):
        ns = [_NumstatCommit(1700000000, "a" * 40, "dev@x.com",
              [(0, 0, "new.py", False)])]
        st = [_NameStatusCommit(1700000000, "a" * 40,
              [_NameStatusEntry(FileStatus.RENAMED, "new.py", "old.py", 100)])]
        result = _merge_commits(ns, st)
        f = result[0].files[0]
        assert f.status == FileStatus.RENAMED
        assert f.old_path == "old.py"
        assert f.rename_score == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git_log.py::TestMergeCommits -v`
Expected: FAIL — cannot import `_merge_commits`

- [ ] **Step 3: Implement merge logic**

Add to `gource_hud/git_log.py`:

```python
def _merge_commits(
    numstat_commits: list[_NumstatCommit],
    name_status_commits: list[_NameStatusCommit],
) -> list[Commit]:
    ns_by_hash = {c.hash: c for c in numstat_commits}
    st_by_hash = {c.hash: c for c in name_status_commits}
    all_hashes = set(ns_by_hash) | set(st_by_hash)
    result: list[Commit] = []

    for h in all_hashes:
        ns = ns_by_hash.get(h)
        st = st_by_hash.get(h)

        timestamp = ns.timestamp if ns else st.timestamp  # type: ignore[union-attr]
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
                commit.files.append(
                    FileChange(
                        path=path,
                        status=entry.status if entry else FileStatus.MODIFIED,
                        adds=adds,
                        deletes=deletes,
                        is_binary=is_binary,
                        old_path=entry.old_path if entry else None,
                        rename_score=entry.score if entry else None,
                    )
                )

        if st:
            for entry in st.entries:
                if entry.path not in seen_paths:
                    commit.files.append(
                        FileChange(
                            path=entry.path,
                            status=entry.status,
                            adds=0,
                            deletes=0,
                            is_binary=False,
                            old_path=entry.old_path,
                            rename_score=entry.score,
                        )
                    )

        result.append(commit)

    result.sort(key=lambda c: (c.timestamp, c.hash))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_git_log.py::TestMergeCommits -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/git_log.py tests/test_git_log.py
git commit -m "feat(git_log): add commit merge logic"
```

---

### Task 6: Anonymizer

**Files:**
- Modify: `gource_hud/git_log.py`
- Modify: `tests/test_git_log.py`

- [ ] **Step 1: Write tests for anonymizer**

Append to `tests/test_git_log.py`:

```python
from gource_hud.git_log import Anonymizer


class TestAnonymizer:
    def test_author_deterministic(self):
        a = Anonymizer()
        assert a.anonymize_author("alice@x.com") == "Dev_1"
        assert a.anonymize_author("bob@x.com") == "Dev_2"
        assert a.anonymize_author("alice@x.com") == "Dev_1"  # same again

    def test_path_preserves_structure(self):
        a = Anonymizer()
        result = a.anonymize_path("src/utils/helper.py")
        parts = result.split("/")
        assert len(parts) == 3
        assert parts[0].startswith("d")
        assert parts[1].startswith("d")
        assert parts[2].startswith("f")
        assert parts[2].endswith(".py")

    def test_shared_dir_segment(self):
        a = Anonymizer()
        p1 = a.anonymize_path("src/a.py")
        p2 = a.anonymize_path("src/b.py")
        assert p1.split("/")[0] == p2.split("/")[0]  # same dir token

    def test_shared_filename_base(self):
        a = Anonymizer()
        p1 = a.anonymize_path("src/foo.py")
        p2 = a.anonymize_path("tests/foo.py")
        # Same base "foo" -> same file token
        assert p1.split("/")[-1] == p2.split("/")[-1]

    def test_dotfile_no_extension(self):
        a = Anonymizer()
        result = a.anonymize_path(".gitignore")
        assert "." not in result  # entire name is base, no extension

    def test_double_extension(self):
        a = Anonymizer()
        result = a.anonymize_path("file.test.py")
        assert result.endswith(".py")

    def test_root_level_file(self):
        a = Anonymizer()
        result = a.anonymize_path("Makefile")
        assert "/" not in result
        assert result.startswith("f")

    def test_deeply_nested(self):
        a = Anonymizer()
        result = a.anonymize_path("a/b/c/d/e/f.txt")
        parts = result.split("/")
        assert len(parts) == 6
        assert all(p.startswith("d") for p in parts[:5])
        assert parts[5].startswith("f")
        assert parts[5].endswith(".txt")

    def test_anonymize_commits(self):
        a = Anonymizer()
        commits = [
            Commit(100, "a" * 40, "alice@x.com", [
                FileChange("src/main.py", FileStatus.MODIFIED, 10, 2, False),
            ]),
            Commit(200, "b" * 40, "bob@x.com", [
                FileChange("src/main.py", FileStatus.MODIFIED, 5, 1, False),
            ]),
        ]
        result = a.anonymize_commits(commits)
        assert len(result) == 2
        assert result[0].author_email == "Dev_1"
        assert result[1].author_email == "Dev_2"
        # Paths should be anonymized and consistent
        assert result[0].files[0].path == result[1].files[0].path

    def test_anonymize_rename_old_path(self):
        a = Anonymizer()
        commits = [
            Commit(100, "a" * 40, "dev@x.com", [
                FileChange("new.py", FileStatus.RENAMED, 0, 0, False,
                           old_path="old.py", rename_score=100),
            ]),
        ]
        result = a.anonymize_commits(commits)
        f = result[0].files[0]
        assert f.old_path is not None
        assert f.old_path.startswith("f")  # anonymized
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git_log.py::TestAnonymizer -v`
Expected: FAIL — cannot import `Anonymizer`

- [ ] **Step 3: Implement Anonymizer**

Add to `gource_hud/git_log.py`:

```python
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
                anon_files.append(
                    FileChange(
                        path=self.anonymize_path(f.path),
                        status=f.status,
                        adds=f.adds,
                        deletes=f.deletes,
                        is_binary=f.is_binary,
                        old_path=self.anonymize_path(f.old_path) if f.old_path else None,
                        rename_score=f.rename_score,
                    )
                )
            result.append(
                Commit(
                    timestamp=c.timestamp,
                    hash=c.hash,
                    author_email=anon_author,
                    files=anon_files,
                )
            )
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_git_log.py::TestAnonymizer -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/git_log.py tests/test_git_log.py
git commit -m "feat(git_log): add Anonymizer class"
```

---

### Task 7: Gource log writer and parse_git_log orchestrator

**Files:**
- Modify: `gource_hud/git_log.py`
- Modify: `tests/test_git_log.py`

- [ ] **Step 1: Write tests for gource log writer**

Append to `tests/test_git_log.py`:

```python
from gource_hud.git_log import write_gource_log
import tempfile
from pathlib import Path


class TestWriteGourceLog:
    def test_basic_output(self):
        commits = [
            Commit(1700000000, "a" * 40, "Dev_1", [
                FileChange("d0001/f0001.py", FileStatus.ADDED, 10, 0, False),
                FileChange("d0001/f0002.py", FileStatus.MODIFIED, 5, 3, False),
                FileChange("d0001/f0003.py", FileStatus.DELETED, 0, 8, False),
            ]),
        ]
        with tempfile.NamedTemporaryFile(mode="r", suffix=".log", delete=False) as f:
            path = Path(f.name)
        try:
            write_gource_log(commits, path)
            lines = path.read_text().splitlines()
            assert len(lines) == 3
            assert lines[0] == "1700000000|Dev_1|A|d0001/f0001.py"
            assert lines[1] == "1700000000|Dev_1|M|d0001/f0002.py"
            assert lines[2] == "1700000000|Dev_1|D|d0001/f0003.py"
        finally:
            path.unlink()

    def test_rename_maps_to_M(self):
        commits = [
            Commit(100, "a" * 40, "dev", [
                FileChange("new.py", FileStatus.RENAMED, 0, 0, False),
            ]),
        ]
        with tempfile.NamedTemporaryFile(mode="r", suffix=".log", delete=False) as f:
            path = Path(f.name)
        try:
            write_gource_log(commits, path)
            assert "|M|" in path.read_text()
        finally:
            path.unlink()

    def test_copy_maps_to_A(self):
        commits = [
            Commit(100, "a" * 40, "dev", [
                FileChange("copy.py", FileStatus.COPIED, 0, 0, False),
            ]),
        ]
        with tempfile.NamedTemporaryFile(mode="r", suffix=".log", delete=False) as f:
            path = Path(f.name)
        try:
            write_gource_log(commits, path)
            assert "|A|" in path.read_text()
        finally:
            path.unlink()

    def test_type_changed_maps_to_M(self):
        commits = [
            Commit(100, "a" * 40, "dev", [
                FileChange("link.txt", FileStatus.TYPE_CHANGED, 0, 0, False),
            ]),
        ]
        with tempfile.NamedTemporaryFile(mode="r", suffix=".log", delete=False) as f:
            path = Path(f.name)
        try:
            write_gource_log(commits, path)
            assert "|M|" in path.read_text()
        finally:
            path.unlink()


class TestRoundTrip:
    def test_anonymized_tokens_only(self):
        """Spec test #18: parse + anonymize produces only valid tokens."""
        import re
        commits = [
            Commit(100, "a" * 40, "alice@real.com", [
                FileChange("src/secret.py", FileStatus.MODIFIED, 10, 2, False),
                FileChange("tests/secret_test.py", FileStatus.ADDED, 5, 0, False),
            ]),
        ]
        anon = Anonymizer()
        result = anon.anonymize_commits(commits)
        for c in result:
            assert re.match(r"^Dev_\d+$", c.author_email)
            for f in c.files:
                parts = f.path.split("/")
                for p in parts[:-1]:  # directories
                    assert re.match(r"^d\d{4}$", p), f"Bad dir token: {p}"
                filename = parts[-1]
                # filename is fNNNN or fNNNN.ext
                assert re.match(r"^f\d{4}(\.\w+)?$", filename), f"Bad file token: {filename}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git_log.py::TestWriteGourceLog tests/test_git_log.py::TestRoundTrip -v`
Expected: FAIL — cannot import `write_gource_log`

- [ ] **Step 3: Implement gource log writer and parse_git_log**

Add to `gource_hud/git_log.py`:

```python
from pathlib import Path

_STATUS_TO_GOURCE_ACTION: dict[FileStatus, str] = {
    FileStatus.ADDED: "A",
    FileStatus.MODIFIED: "M",
    FileStatus.DELETED: "D",
    FileStatus.RENAMED: "M",
    FileStatus.COPIED: "A",
    FileStatus.TYPE_CHANGED: "M",
}


def write_gource_log(commits: list[Commit], output_path: Path) -> None:
    with open(output_path, "w") as f:
        for commit in commits:
            action_default = "M"
            for file in commit.files:
                action = _STATUS_TO_GOURCE_ACTION.get(file.status, action_default)
                f.write(f"{commit.timestamp}|{commit.author_email}|{action}|{file.path}\n")


def parse_git_log(repo_path: str, since: str) -> list[Commit]:
    result_a = subprocess.run(
        [
            "git", "log", f"--since={since}", "--numstat",
            "--format=%ct%x09%H%x09%ae", "--no-merges",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        cwd=repo_path,
    )
    result_b = subprocess.run(
        [
            "git", "log", f"--since={since}", "--name-status",
            "--format=%ct%x09%H", "--no-merges",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        cwd=repo_path,
    )
    numstat_commits = _parse_numstat_output(result_a.stdout)
    name_status_commits = _parse_name_status_output(result_b.stdout)
    return _merge_commits(numstat_commits, name_status_commits)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_git_log.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/git_log.py tests/test_git_log.py
git commit -m "feat(git_log): add gource log writer and parse_git_log orchestrator"
```

---

## Chunk 2: stats.py

### Task 8: Day bucketing

**Files:**
- Create: `gource_hud/stats.py`
- Create: `tests/test_stats.py`

- [ ] **Step 1: Write tests for day bucketing**

```python
# tests/test_stats.py
from gource_hud.stats import DayBucket, bucket_commits
from gource_hud.git_log import Commit, FileChange, FileStatus

DAY = 86400


class TestBucketCommits:
    def test_single_commit(self):
        commits = [
            Commit(DAY * 10, "a" * 40, "alice", [
                FileChange("a.py", FileStatus.MODIFIED, 10, 2, False),
            ]),
        ]
        days, buckets = bucket_commits(commits)
        assert days == [DAY * 10]
        b = buckets[DAY * 10]
        assert b.loc_added == 10
        assert b.loc_deleted == 2
        assert b.commit_count == 1
        assert b.authors == {"alice"}
        assert b.files_changed == {"a.py"}

    def test_gap_filling(self):
        commits = [
            Commit(DAY * 0, "a" * 40, "alice", [
                FileChange("a.py", FileStatus.ADDED, 20, 0, False),
            ]),
            Commit(DAY * 3, "b" * 40, "bob", [
                FileChange("b.py", FileStatus.ADDED, 10, 0, False),
            ]),
        ]
        days, buckets = bucket_commits(commits)
        assert len(days) == 4  # days 0, 1, 2, 3
        assert buckets[DAY * 1].commit_count == 0
        assert buckets[DAY * 1].authors == set()
        assert buckets[DAY * 2].loc_added == 0

    def test_multiple_commits_same_day(self):
        commits = [
            Commit(DAY * 5, "a" * 40, "alice", [
                FileChange("a.py", FileStatus.MODIFIED, 10, 0, False),
            ]),
            Commit(DAY * 5 + 3600, "b" * 40, "bob", [
                FileChange("b.py", FileStatus.ADDED, 5, 0, False),
            ]),
        ]
        days, buckets = bucket_commits(commits)
        assert len(days) == 1
        b = buckets[DAY * 5]
        assert b.commit_count == 2
        assert b.authors == {"alice", "bob"}
        assert b.loc_added == 15
        assert b.files_added_count == 1  # only b.py is ADDED

    def test_files_added_deleted(self):
        commits = [
            Commit(DAY * 0, "a" * 40, "dev", [
                FileChange("new.py", FileStatus.ADDED, 10, 0, False),
                FileChange("old.py", FileStatus.DELETED, 0, 8, False),
            ]),
        ]
        days, buckets = bucket_commits(commits)
        b = buckets[DAY * 0]
        assert b.files_added_count == 1
        assert b.files_deleted_count == 1

    def test_empty_input(self):
        days, buckets = bucket_commits([])
        assert days == []
        assert buckets == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stats.py -v`
Expected: FAIL — cannot import `DayBucket`, `bucket_commits`

- [ ] **Step 3: Implement day bucketing**

```python
# gource_hud/stats.py
from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

from gource_hud.git_log import Commit, FileStatus

DAY_SECONDS = 86400


@dataclass
class DayBucket:
    timestamp: int
    loc_added: int = 0
    loc_deleted: int = 0
    commit_count: int = 0
    authors: set[str] = field(default_factory=set)
    files_changed: set[str] = field(default_factory=set)
    files_added_count: int = 0
    files_deleted_count: int = 0


def bucket_commits(commits: list[Commit]) -> tuple[list[int], dict[int, DayBucket]]:
    buckets: dict[int, DayBucket] = {}

    for commit in commits:
        day = (commit.timestamp // DAY_SECONDS) * DAY_SECONDS
        if day not in buckets:
            buckets[day] = DayBucket(timestamp=day)
        b = buckets[day]
        b.commit_count += 1
        b.authors.add(commit.author_email)
        for f in commit.files:
            b.loc_added += f.adds
            b.loc_deleted += f.deletes
            b.files_changed.add(f.path)
            if f.status == FileStatus.ADDED:
                b.files_added_count += 1
            elif f.status == FileStatus.DELETED:
                b.files_deleted_count += 1

    if not buckets:
        return [], {}

    min_day = min(buckets)
    max_day = max(buckets)
    days: list[int] = []
    t = min_day
    while t <= max_day:
        if t not in buckets:
            buckets[t] = DayBucket(timestamp=t)
        days.append(t)
        t += DAY_SECONDS

    return days, buckets
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stats.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/stats.py tests/test_stats.py
git commit -m "feat(stats): add day bucketing with gap filling"
```

---

### Task 9: Rolling sum and rolling unique count

**Files:**
- Modify: `gource_hud/stats.py`
- Modify: `tests/test_stats.py`

- [ ] **Step 1: Write tests for rolling functions**

Append to `tests/test_stats.py`:

```python
from gource_hud.stats import rolling_sum, rolling_unique_count

DAY = 86400


class TestRollingSum:
    def test_1d_window(self):
        days = [DAY * i for i in range(3)]
        values = {DAY * 0: 10, DAY * 1: 5, DAY * 2: 3}
        result = rolling_sum(days, values, DAY)
        assert result == {DAY * 0: 10, DAY * 1: 5, DAY * 2: 3}

    def test_7d_window_accumulates(self):
        days = [DAY * i for i in range(3)]
        values = {DAY * 0: 10, DAY * 1: 5, DAY * 2: 3}
        result = rolling_sum(days, values, 7 * DAY)
        assert result[DAY * 0] == 10
        assert result[DAY * 1] == 15
        assert result[DAY * 2] == 18

    def test_eviction(self):
        days = [DAY * i for i in range(8)]
        values = {d: (100 if d == 0 else 0) for d in days}
        result = rolling_sum(days, values, 7 * DAY)
        # Day 0 value is 100. At day 7, day 0 should be evicted.
        assert result[DAY * 6] == 100  # still in window
        assert result[DAY * 7] == 0    # evicted

    def test_empty(self):
        assert rolling_sum([], {}, DAY) == {}


class TestRollingUniqueCount:
    def test_single_author_all_days(self):
        days = [DAY * i for i in range(3)]
        sets = {d: {"alice"} for d in days}
        result = rolling_unique_count(days, sets, 7 * DAY)
        assert all(v == 1 for v in result.values())

    def test_new_author_added(self):
        days = [DAY * i for i in range(3)]
        sets = {DAY * 0: {"alice"}, DAY * 1: {"alice", "bob"}, DAY * 2: {"carol"}}
        result = rolling_unique_count(days, sets, 7 * DAY)
        assert result[DAY * 0] == 1
        assert result[DAY * 1] == 2
        assert result[DAY * 2] == 3

    def test_eviction_removes_unique(self):
        # Alice only on day 0, evicted at day 7
        days = [DAY * i for i in range(8)]
        sets = {d: set() for d in days}
        sets[DAY * 0] = {"alice"}
        sets[DAY * 1] = {"bob"}
        sets[DAY * 7] = {"carol"}
        result = rolling_unique_count(days, sets, 7 * DAY)
        assert result[DAY * 6] == 2   # alice + bob
        assert result[DAY * 7] == 2   # bob + carol (alice evicted)

    def test_partial_eviction(self):
        # Alice on days 0 and 2. Evict day 0 at day 7; alice still on day 2.
        days = [DAY * i for i in range(8)]
        sets = {d: set() for d in days}
        sets[DAY * 0] = {"alice"}
        sets[DAY * 2] = {"alice"}
        result = rolling_unique_count(days, sets, 7 * DAY)
        assert result[DAY * 7] == 1  # alice still present via day 2

    def test_empty(self):
        assert rolling_unique_count([], {}, DAY) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stats.py -v -k "Rolling"`
Expected: FAIL — cannot import `rolling_sum`, `rolling_unique_count`

- [ ] **Step 3: Implement rolling functions**

Add to `gource_hud/stats.py`:

```python
def rolling_sum(
    days: list[int], values: dict[int, int], window_seconds: int
) -> dict[int, int]:
    result: dict[int, int] = {}
    queue: deque[tuple[int, int]] = deque()
    running = 0

    for t in days:
        v = values[t]
        queue.append((t, v))
        running += v
        while queue and (t - queue[0][0]) >= window_seconds:
            running -= queue[0][1]
            queue.popleft()
        result[t] = running

    return result


def rolling_unique_count(
    days: list[int], sets_by_day: dict[int, set[str]], window_seconds: int
) -> dict[int, int]:
    result: dict[int, int] = {}
    queue: deque[tuple[int, set[str]]] = deque()
    counter: Counter[str] = Counter()

    for t in days:
        new_set = sets_by_day[t]
        queue.append((t, new_set))
        for elem in new_set:
            counter[elem] += 1
        while queue and (t - queue[0][0]) >= window_seconds:
            _, old_set = queue.popleft()
            for elem in old_set:
                counter[elem] -= 1
                if counter[elem] == 0:
                    del counter[elem]
        result[t] = len(counter)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stats.py -v -k "Rolling"`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/stats.py tests/test_stats.py
git commit -m "feat(stats): add rolling_sum and rolling_unique_count"
```

---

### Task 10: Running maxima, cumulative series, percentile

**Files:**
- Modify: `gource_hud/stats.py`
- Modify: `tests/test_stats.py`

- [ ] **Step 1: Write tests**

Append to `tests/test_stats.py`:

```python
from gource_hud.stats import running_maxima, cumulative_series, percentile

DAY = 86400


class TestRunningMaxima:
    def test_increasing(self):
        days = [DAY * i for i in range(3)]
        values = {DAY * 0: 5, DAY * 1: 10, DAY * 2: 3}
        result = running_maxima(days, values)
        assert result == {DAY * 0: 5, DAY * 1: 10, DAY * 2: 10}

    def test_empty(self):
        assert running_maxima([], {}) == {}


class TestCumulativeSeries:
    def test_basic(self):
        days = [DAY * i for i in range(3)]
        values = {DAY * 0: 8, DAY * 1: 5, DAY * 2: 2}
        result = cumulative_series(days, values)
        assert result == {DAY * 0: 8, DAY * 1: 13, DAY * 2: 15}

    def test_negative_deltas(self):
        days = [DAY * i for i in range(3)]
        values = {DAY * 0: -5, DAY * 1: -10, DAY * 2: 0}
        result = cumulative_series(days, values)
        assert result == {DAY * 0: -5, DAY * 1: -15, DAY * 2: -15}

    def test_empty(self):
        assert cumulative_series([], {}) == {}


class TestPercentile:
    def test_empty(self):
        assert percentile([], 0.5) == 0

    def test_single_value(self):
        assert percentile([42], 0.5) == 42
        assert percentile([42], 0.9) == 42

    def test_two_values_median(self):
        assert percentile([10, 20], 0.5) == 15

    def test_two_values_p90(self):
        assert percentile([10, 20], 0.9) == 19

    def test_three_values_median(self):
        assert percentile([10, 20, 30], 0.5) == 20

    def test_three_values_p90(self):
        assert percentile([10, 20, 30], 0.9) == 28

    def test_five_values_p90(self):
        # k = 4 * 0.9 = 3.6, f=3, c=4
        # v[3]*(4-3.6) + v[4]*(3.6-3) = 4*0.4 + 5*0.6 = 4.6 -> round -> 5
        assert percentile([1, 2, 3, 4, 5], 0.9) == 5

    def test_six_values(self):
        assert percentile([1, 3, 5, 7, 9, 11], 0.5) == 6
        assert percentile([1, 3, 5, 7, 9, 11], 0.9) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stats.py -v -k "Maxima or Cumulative or Percentile"`
Expected: FAIL

- [ ] **Step 3: Implement**

Add to `gource_hud/stats.py`:

```python
def running_maxima(days: list[int], values: dict[int, int]) -> dict[int, int]:
    result: dict[int, int] = {}
    max_so_far = 0
    for t in days:
        v = values[t]
        if v > max_so_far:
            max_so_far = v
        result[t] = max_so_far
    return result


def cumulative_series(days: list[int], values: dict[int, int]) -> dict[int, int]:
    result: dict[int, int] = {}
    running = 0
    for t in days:
        running += values[t]
        result[t] = running
    return result


def percentile(sorted_values: list[int], p: float) -> int:
    if not sorted_values:
        return 0
    n = len(sorted_values)
    k = (n - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return int(round(sorted_values[f] * (c - k) + sorted_values[c] * (k - f)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stats.py -v -k "Maxima or Cumulative or Percentile"`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/stats.py tests/test_stats.py
git commit -m "feat(stats): add running_maxima, cumulative_series, percentile"
```

---

### Task 11: Derived metrics — churn, efficiency, trends, language mix, change size

**Files:**
- Modify: `gource_hud/stats.py`
- Modify: `tests/test_stats.py`

- [ ] **Step 1: Write tests for derived metrics**

Append to `tests/test_stats.py`:

```python
from gource_hud.stats import (
    compute_churn, compute_efficiency, compute_wow_delta,
    format_trend_arrow, lang_from_path, EXTENSION_TO_LANGUAGE,
    compute_language_mix_7d, compute_change_size_distribution_7d,
)

DAY = 86400


class TestChurnEfficiency:
    def test_churn_zero_total(self):
        assert compute_churn(0, 0) == 0

    def test_churn_pure_adds(self):
        assert compute_churn(100, 0) == 0

    def test_churn_pure_deletes(self):
        assert compute_churn(0, 100) == 100

    def test_churn_even(self):
        assert compute_churn(50, 50) == 50

    def test_churn_rounding(self):
        assert compute_churn(1, 2) == 67  # round(200/3)

    def test_efficiency_zero_total(self):
        assert compute_efficiency(0, 0) == 0

    def test_efficiency_pure_adds(self):
        assert compute_efficiency(100, 0) == 100

    def test_efficiency_pure_deletes(self):
        assert compute_efficiency(0, 100) == -100

    def test_efficiency_even(self):
        assert compute_efficiency(50, 50) == 0

    def test_efficiency_negative(self):
        assert compute_efficiency(1, 2) == -33


class TestTrends:
    def test_wow_delta_sufficient_history(self):
        values = [10, 20, 30, 40, 50, 60, 70, 80]
        assert compute_wow_delta(values, 7) == 70  # 80 - 10

    def test_wow_delta_insufficient_history(self):
        values = [10, 20, 30]
        assert compute_wow_delta(values, 2) == 0

    def test_format_arrow_positive(self):
        assert format_trend_arrow(5) == "▲ +5"

    def test_format_arrow_negative(self):
        assert format_trend_arrow(-3) == "▼ 3"

    def test_format_arrow_zero(self):
        assert format_trend_arrow(0) == "– 0"


class TestLangFromPath:
    def test_python(self):
        assert lang_from_path("src/main.py") == "python"

    def test_typescript(self):
        assert lang_from_path("lib/utils.tsx") == "typescript"

    def test_unknown(self):
        assert lang_from_path("Makefile") == "other"

    def test_dotfile(self):
        assert lang_from_path(".gitignore") == "other"

    def test_double_extension(self):
        assert lang_from_path("foo.test.js") == "javascript"


class TestLanguageMix7d:
    def test_single_language(self):
        days = [DAY * 0]
        lang_loc = {DAY * 0: {"python": 100}}
        result = compute_language_mix_7d(days, lang_loc)
        assert result[DAY * 0] == [("python", 100)]

    def test_top_3_only(self):
        days = [DAY * 0]
        lang_loc = {DAY * 0: {"a": 40, "b": 30, "c": 20, "d": 10}}
        result = compute_language_mix_7d(days, lang_loc)
        assert len(result[DAY * 0]) == 3
        assert result[DAY * 0][0][0] == "a"

    def test_eviction(self):
        days = [DAY * i for i in range(8)]
        lang_loc: dict[int, dict[str, int]] = {d: {} for d in days}
        lang_loc[DAY * 0] = {"python": 1000}
        lang_loc[DAY * 7] = {"go": 100}
        result = compute_language_mix_7d(days, lang_loc)
        # Day 7: python evicted, only go
        assert result[DAY * 7] == [("go", 100)]

    def test_empty_window(self):
        days = [DAY * 0]
        lang_loc: dict[int, dict[str, int]] = {DAY * 0: {}}
        result = compute_language_mix_7d(days, lang_loc)
        assert result[DAY * 0] == []


class TestChangeSizeDistribution7d:
    def test_basic(self):
        days = [DAY * 0]
        sizes = {DAY * 0: [10, 30, 50]}
        result = compute_change_size_distribution_7d(days, sizes)
        # median of [10,30,50] = 30, p90: k=2*0.9=1.8, 30*0.2+50*0.8=46
        assert result[DAY * 0] == (30, 46)

    def test_empty_window(self):
        days = [DAY * 0]
        sizes: dict[int, list[int]] = {DAY * 0: []}
        result = compute_change_size_distribution_7d(days, sizes)
        assert result[DAY * 0] == (0, 0)

    def test_eviction(self):
        days = [DAY * i for i in range(8)]
        sizes: dict[int, list[int]] = {d: [] for d in days}
        sizes[DAY * 0] = [1000]
        sizes[DAY * 7] = [10]
        result = compute_change_size_distribution_7d(days, sizes)
        # Day 7: 1000 evicted, only [10]
        assert result[DAY * 7] == (10, 10)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stats.py -v -k "Churn or Trend or Lang or ChangeSize"`
Expected: FAIL

- [ ] **Step 3: Implement derived metrics**

Add to `gource_hud/stats.py`:

```python
def compute_churn(adds: int, deletes: int) -> int:
    total = adds + deletes
    if total == 0:
        return 0
    return int(round(100 * deletes / total))


def compute_efficiency(adds: int, deletes: int) -> int:
    total = adds + deletes
    if total == 0:
        return 0
    return int(round(100 * (adds - deletes) / total))


def compute_wow_delta(values: list[int], index: int, step: int = 7) -> int:
    if index < step:
        return 0
    return values[index] - values[index - step]


def format_trend_arrow(delta: int) -> str:
    if delta > 0:
        return f"▲ +{delta}"
    elif delta < 0:
        return f"▼ {abs(delta)}"
    return "– 0"


EXTENSION_TO_LANGUAGE: dict[str, str] = {
    "py": "python", "pyi": "python", "pyx": "python", "ipynb": "python",
    "ts": "typescript", "tsx": "typescript", "mts": "typescript", "cts": "typescript",
    "js": "javascript", "jsx": "javascript", "mjs": "javascript", "cjs": "javascript",
    "go": "go",
    "rs": "rust",
    "java": "java",
    "kt": "kotlin", "kts": "kotlin",
    "rb": "ruby", "rake": "ruby", "gemspec": "ruby",
    "php": "php",
    "c": "c", "h": "c",
    "cc": "c++", "cpp": "c++", "cxx": "c++", "hh": "c++", "hpp": "c++", "hxx": "c++",
    "cs": "c#",
    "swift": "swift",
    "m": "obj-c", "mm": "obj-c",
    "sh": "shell", "bash": "shell", "zsh": "shell", "fish": "shell",
    "yml": "yaml", "yaml": "yaml",
    "json": "json",
    "toml": "toml",
    "md": "markdown", "mdx": "markdown",
    "sql": "sql",
    "r": "r",
    "jl": "julia",
    "scala": "scala", "sc": "scala",
}


def lang_from_path(path: str) -> str:
    filename = path.rsplit("/", 1)[-1]
    if "." not in filename:
        return "other"
    ext = filename.rsplit(".", 1)[-1].lower()
    return EXTENSION_TO_LANGUAGE.get(ext, "other")


def compute_language_mix_7d(
    days: list[int],
    lang_loc_day: dict[int, dict[str, int]],
) -> dict[int, list[tuple[str, int]]]:
    result: dict[int, list[tuple[str, int]]] = {}
    window: deque[int] = deque()
    counter: Counter[str] = Counter()

    for t in days:
        window.append(t)
        for lang, loc in lang_loc_day.get(t, {}).items():
            counter[lang] += loc
        while len(window) > 7:
            old_t = window.popleft()
            for lang, loc in lang_loc_day.get(old_t, {}).items():
                counter[lang] -= loc
                if counter[lang] <= 0:
                    del counter[lang]
        total = sum(counter.values())
        if total > 0:
            top3 = counter.most_common(3)
            result[t] = [(lang, int(round(100 * loc / total))) for lang, loc in top3]
        else:
            result[t] = []

    return result


def compute_change_size_distribution_7d(
    days: list[int],
    sizes_on_day: dict[int, list[int]],
) -> dict[int, tuple[int, int]]:
    result: dict[int, tuple[int, int]] = {}
    window: deque[int] = deque()
    window_sizes: list[int] = []

    for t in days:
        window.append(t)
        window_sizes.extend(sizes_on_day.get(t, []))
        while len(window) > 7:
            old_t = window.popleft()
            for s in sizes_on_day.get(old_t, []):
                window_sizes.remove(s)
        if not window_sizes:
            result[t] = (0, 0)
        else:
            sv = sorted(window_sizes)
            result[t] = (percentile(sv, 0.5), percentile(sv, 0.9))

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stats.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/stats.py tests/test_stats.py
git commit -m "feat(stats): add derived metrics — churn, efficiency, trends, language mix, change size"
```

---

### Task 12: DayMetrics and compute_all_metrics orchestrator

**Files:**
- Modify: `gource_hud/stats.py`
- Modify: `tests/test_stats.py`

- [ ] **Step 1: Write tests for compute_all_metrics**

Append to `tests/test_stats.py`:

```python
from gource_hud.stats import DayMetrics, compute_all_metrics

DAY = 86400


class TestComputeAllMetrics:
    def test_empty_input(self):
        assert compute_all_metrics([]) == []

    def test_single_day(self):
        commits = [
            Commit(DAY * 10, "a" * 40, "alice", [
                FileChange("main.py", FileStatus.MODIFIED, 42, 7, False),
            ]),
        ]
        result = compute_all_metrics(commits)
        assert len(result) == 1
        m = result[0]
        assert m.timestamp == DAY * 10
        assert m.loc_added_1d == 42
        assert m.loc_deleted_1d == 7
        assert m.commits_1d == 1
        assert m.authors_1d == 1
        assert m.max_loc_total_1d == 49
        assert m.cumulative_loc_delta == 35
        assert m.cumulative_files_delta == 0  # MODIFIED, not ADDED

    def test_three_days(self):
        commits = [
            Commit(DAY * 10, "a" * 40, "alice", [
                FileChange("a.py", FileStatus.MODIFIED, 10, 2, False),
            ]),
            Commit(DAY * 11, "b" * 40, "alice", [
                FileChange("b.py", FileStatus.ADDED, 5, 0, False),
            ]),
            Commit(DAY * 12, "c" * 40, "alice", [
                FileChange("a.py", FileStatus.MODIFIED, 3, 1, False),
            ]),
        ]
        result = compute_all_metrics(commits)
        assert len(result) == 3
        # Day 12 (index 2): 7d should accumulate all 3 days
        m = result[2]
        assert m.loc_added_7d == 18  # 10 + 5 + 3
        assert m.loc_deleted_7d == 3  # 2 + 0 + 1
        assert m.commits_7d == 3
        assert m.cumulative_loc_delta == 15  # (10-2) + (5-0) + (3-1)
        assert m.cumulative_files_delta == 1  # 1 ADDED file total

    def test_has_derived_metrics(self):
        commits = [
            Commit(DAY * 10, "a" * 40, "alice", [
                FileChange("a.py", FileStatus.MODIFIED, 80, 20, False),
            ]),
        ]
        result = compute_all_metrics(commits)
        m = result[0]
        assert m.churn_7d == 20  # 20 / 100
        assert m.efficiency_7d == 60  # 60 / 100
        assert m.arrow_loc == "– 0"  # no history for WoW
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stats.py::TestComputeAllMetrics -v`
Expected: FAIL — cannot import `DayMetrics`, `compute_all_metrics`

- [ ] **Step 3: Implement DayMetrics and orchestrator**

Add to `gource_hud/stats.py`:

```python
@dataclass
class DayMetrics:
    timestamp: int

    loc_added_1d: int = 0
    loc_added_7d: int = 0
    loc_added_30d: int = 0
    loc_deleted_1d: int = 0
    loc_deleted_7d: int = 0
    loc_deleted_30d: int = 0

    commits_1d: int = 0
    commits_7d: int = 0
    commits_30d: int = 0

    authors_1d: int = 0
    authors_7d: int = 0
    authors_30d: int = 0

    files_changed_1d: int = 0
    files_changed_7d: int = 0
    files_changed_30d: int = 0

    files_added_1d: int = 0
    files_added_7d: int = 0
    files_added_30d: int = 0
    files_deleted_1d: int = 0
    files_deleted_7d: int = 0
    files_deleted_30d: int = 0

    max_loc_total_1d: int = 0
    max_loc_total_7d: int = 0
    max_loc_total_30d: int = 0

    cumulative_loc_delta: int = 0
    cumulative_files_delta: int = 0

    churn_7d: int = 0
    churn_30d: int = 0
    efficiency_7d: int = 0
    efficiency_30d: int = 0

    delta_loc_7d: int = 0
    delta_commits_7d: int = 0
    delta_files_7d: int = 0
    arrow_loc: str = "– 0"
    arrow_commits: str = "– 0"
    arrow_files: str = "– 0"

    lang_mix_7d: list[tuple[str, int]] = field(default_factory=list)
    change_median_7d: int = 0
    change_p90_7d: int = 0


W1 = DAY_SECONDS
W7 = 7 * DAY_SECONDS
W30 = 30 * DAY_SECONDS


def compute_all_metrics(commits: list[Commit]) -> list[DayMetrics]:
    days, buckets = bucket_commits(commits)
    if not days:
        return []

    loc_add = {t: buckets[t].loc_added for t in days}
    loc_del = {t: buckets[t].loc_deleted for t in days}
    commit_ct = {t: buckets[t].commit_count for t in days}
    author_sets = {t: buckets[t].authors for t in days}
    file_sets = {t: buckets[t].files_changed for t in days}
    files_add = {t: buckets[t].files_added_count for t in days}
    files_del = {t: buckets[t].files_deleted_count for t in days}

    windows = [W1, W7, W30]
    r_add = {w: rolling_sum(days, loc_add, w) for w in windows}
    r_del = {w: rolling_sum(days, loc_del, w) for w in windows}
    r_cmt = {w: rolling_sum(days, commit_ct, w) for w in windows}
    r_fadd = {w: rolling_sum(days, files_add, w) for w in windows}
    r_fdel = {w: rolling_sum(days, files_del, w) for w in windows}
    r_auth = {w: rolling_unique_count(days, author_sets, w) for w in windows}
    r_fchg = {w: rolling_unique_count(days, file_sets, w) for w in windows}

    loc_total = {w: {t: r_add[w][t] + r_del[w][t] for t in days} for w in windows}
    max_loc = {w: running_maxima(days, loc_total[w]) for w in windows}

    loc_delta = {t: loc_add[t] - loc_del[t] for t in days}
    files_delta = {t: files_add[t] - files_del[t] for t in days}
    cum_loc = cumulative_series(days, loc_delta)
    cum_files = cumulative_series(days, files_delta)

    # Language mix
    lang_loc_day: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for commit in commits:
        day = (commit.timestamp // DAY_SECONDS) * DAY_SECONDS
        for f in commit.files:
            lang = lang_from_path(f.path)
            lang_loc_day[day][lang] += f.adds + f.deletes
    lang_mix = compute_language_mix_7d(days, dict(lang_loc_day))

    # Change size
    sizes_on_day: dict[int, list[int]] = defaultdict(list)
    for commit in commits:
        day = (commit.timestamp // DAY_SECONDS) * DAY_SECONDS
        total = sum(f.adds + f.deletes for f in commit.files)
        sizes_on_day[day].append(total)
    change_dist = compute_change_size_distribution_7d(days, dict(sizes_on_day))

    # WoW series
    net7_list = [r_add[W7][t] - r_del[W7][t] for t in days]
    cmt7_list = [r_cmt[W7][t] for t in days]
    fchg7_list = [r_fchg[W7][t] for t in days]

    result: list[DayMetrics] = []
    for i, t in enumerate(days):
        d_loc = compute_wow_delta(net7_list, i)
        d_cmt = compute_wow_delta(cmt7_list, i)
        d_fch = compute_wow_delta(fchg7_list, i)
        med, p90 = change_dist[t]

        m = DayMetrics(
            timestamp=t,
            loc_added_1d=r_add[W1][t], loc_added_7d=r_add[W7][t], loc_added_30d=r_add[W30][t],
            loc_deleted_1d=r_del[W1][t], loc_deleted_7d=r_del[W7][t], loc_deleted_30d=r_del[W30][t],
            commits_1d=r_cmt[W1][t], commits_7d=r_cmt[W7][t], commits_30d=r_cmt[W30][t],
            authors_1d=r_auth[W1][t], authors_7d=r_auth[W7][t], authors_30d=r_auth[W30][t],
            files_changed_1d=r_fchg[W1][t], files_changed_7d=r_fchg[W7][t], files_changed_30d=r_fchg[W30][t],
            files_added_1d=r_fadd[W1][t], files_added_7d=r_fadd[W7][t], files_added_30d=r_fadd[W30][t],
            files_deleted_1d=r_fdel[W1][t], files_deleted_7d=r_fdel[W7][t], files_deleted_30d=r_fdel[W30][t],
            max_loc_total_1d=max_loc[W1][t], max_loc_total_7d=max_loc[W7][t], max_loc_total_30d=max_loc[W30][t],
            cumulative_loc_delta=cum_loc[t],
            cumulative_files_delta=cum_files[t],
            churn_7d=compute_churn(r_add[W7][t], r_del[W7][t]),
            churn_30d=compute_churn(r_add[W30][t], r_del[W30][t]),
            efficiency_7d=compute_efficiency(r_add[W7][t], r_del[W7][t]),
            efficiency_30d=compute_efficiency(r_add[W30][t], r_del[W30][t]),
            delta_loc_7d=d_loc, delta_commits_7d=d_cmt, delta_files_7d=d_fch,
            arrow_loc=format_trend_arrow(d_loc),
            arrow_commits=format_trend_arrow(d_cmt),
            arrow_files=format_trend_arrow(d_fch),
            lang_mix_7d=lang_mix[t],
            change_median_7d=med,
            change_p90_7d=p90,
        )
        result.append(m)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stats.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/stats.py tests/test_stats.py
git commit -m "feat(stats): add DayMetrics dataclass and compute_all_metrics orchestrator"
```

---

## Chunk 3: overlay.py

### Task 13: Layout computation

**Files:**
- Create: `gource_hud/overlay.py`
- Create: `tests/test_overlay.py`

- [ ] **Step 1: Write tests for layout computation**

```python
# tests/test_overlay.py
from gource_hud.overlay import compute_layout, LayoutMetrics


class TestComputeLayout:
    def test_1080p(self):
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        assert layout.font_size == 14
        assert layout.line_gap == 18  # int(14 * 1.35)
        assert layout.pad_x == 16
        assert layout.pad_y == 12
        assert layout.graph_h == 140
        assert layout.graph_gap == 14
        assert layout.panel_w == 640
        assert layout.panel_h == 720
        assert layout.rect_x1 == 0
        assert layout.rect_y1 == 360  # 1080 - 720
        assert layout.rect_x2 == 640
        assert layout.rect_y2 == 1080

    def test_4k(self):
        layout = compute_layout(3840, 2160, 2.0, 14, 640)
        assert layout.font_size == 28
        assert layout.line_gap == 37  # int(28 * 1.35)
        assert layout.panel_w == 1280

    def test_text_above_graph1(self):
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        text_bottom = layout.text_y_start + 13 * layout.line_gap
        assert text_bottom <= layout.graph1_bbox[1]

    def test_graphs_dont_overlap(self):
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        assert layout.graph1_bbox[3] <= layout.graph2_bbox[1]
        assert layout.graph2_bbox[3] <= layout.graph3_bbox[1]

    def test_panel_fits_in_frame(self):
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        assert layout.rect_y1 >= 0
        assert layout.rect_x2 <= 1920
        assert layout.rect_y2 == 1080
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_overlay.py -v`
Expected: FAIL — cannot import `compute_layout`

- [ ] **Step 3: Implement layout computation**

```python
# gource_hud/overlay.py
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gource_hud.stats import DayMetrics

N_LINES = 13
N_GRAPHS = 3


@dataclass
class LayoutMetrics:
    scale: float
    font_size: int
    line_gap: int
    pad_x: int
    pad_y: int
    graph_h: int
    graph_gap: int
    panel_w: int
    panel_h: int
    rect_x1: int
    rect_y1: int
    rect_x2: int
    rect_y2: int
    graph1_bbox: tuple[int, int, int, int]
    graph2_bbox: tuple[int, int, int, int]
    graph3_bbox: tuple[int, int, int, int]
    text_x: int
    text_y_start: int
    stroke_width: int
    polyline_width: int


def compute_layout(
    frame_w: int, frame_h: int, scale: float,
    font_size_base: int, panel_width_base: int,
) -> LayoutMetrics:
    font_size = int(font_size_base * scale)
    line_gap = int(font_size * 1.35)
    pad_x = int(16 * scale)
    pad_y = int(12 * scale)
    graph_h = int(140 * scale)
    graph_gap = int(14 * scale)
    panel_w = int(panel_width_base * scale)

    text_h = N_LINES * line_gap
    panel_h = pad_y + text_h + graph_gap + N_GRAPHS * graph_h + (N_GRAPHS - 1) * graph_gap + pad_y

    rect_x1 = 0
    rect_y1 = frame_h - panel_h
    rect_x2 = panel_w
    rect_y2 = frame_h

    gx1 = pad_x
    gx2 = panel_w - pad_x

    g3_y2 = rect_y2 - pad_y
    g3_y1 = g3_y2 - graph_h
    g2_y2 = g3_y1 - graph_gap
    g2_y1 = g2_y2 - graph_h
    g1_y2 = g2_y1 - graph_gap
    g1_y1 = g1_y2 - graph_h

    return LayoutMetrics(
        scale=scale,
        font_size=font_size,
        line_gap=line_gap,
        pad_x=pad_x,
        pad_y=pad_y,
        graph_h=graph_h,
        graph_gap=graph_gap,
        panel_w=panel_w,
        panel_h=panel_h,
        rect_x1=rect_x1,
        rect_y1=rect_y1,
        rect_x2=rect_x2,
        rect_y2=rect_y2,
        graph1_bbox=(gx1, g1_y1, gx2, g1_y2),
        graph2_bbox=(gx1, g2_y1, gx2, g2_y2),
        graph3_bbox=(gx1, g3_y1, gx2, g3_y2),
        text_x=pad_x,
        text_y_start=rect_y1 + pad_y,
        stroke_width=max(1, int(scale)),
        polyline_width=max(2, int(2 * scale)),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_overlay.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/overlay.py tests/test_overlay.py
git commit -m "feat(overlay): add layout computation"
```

---

### Task 14: Text formatting and graph series precomputation

**Files:**
- Modify: `gource_hud/overlay.py`
- Modify: `tests/test_overlay.py`

- [ ] **Step 1: Write tests**

Append to `tests/test_overlay.py`:

```python
from gource_hud.overlay import (
    thousands, fmt, compute_format_widths, format_day_lines,
    compute_graph_series, GraphSeries,
)
from gource_hud.stats import DayMetrics


class TestFormatting:
    def test_thousands(self):
        assert thousands(0) == "0"
        assert thousands(999) == "999"
        assert thousands(1000) == "1,000"
        assert thousands(1234567) == "1,234,567"
        assert thousands(-42) == "-42"

    def test_fmt_right_justify(self):
        assert fmt(42, 7) == "     42"
        assert fmt(1000, 7) == "  1,000"

    def test_format_day_lines_count(self):
        m = DayMetrics(timestamp=0)
        widths = compute_format_widths([m])
        lines = format_day_lines([m], widths)
        assert len(lines) == 1
        assert len(lines[0]) == 13

    def test_format_day_lines_fixed_width(self):
        m1 = DayMetrics(timestamp=0, loc_added_1d=10, loc_deleted_1d=2)
        m2 = DayMetrics(timestamp=86400, loc_added_1d=1000, loc_deleted_1d=500)
        widths = compute_format_widths([m1, m2])
        lines = format_day_lines([m1, m2], widths)
        # Each line index should have same length across all days
        for line_idx in range(13):
            assert len(lines[0][line_idx]) == len(lines[1][line_idx])


class TestGraphSeries:
    def test_cumulative_loc(self):
        metrics = [
            DayMetrics(timestamp=0, cumulative_loc_delta=7),
            DayMetrics(timestamp=86400, cumulative_loc_delta=22),
            DayMetrics(timestamp=172800, cumulative_loc_delta=25),
        ]
        series = compute_graph_series(metrics)
        assert series.cum_loc == [7, 22, 25]
        assert series.cum_loc_min == 7
        assert series.cum_loc_range == 18  # 25 - 7

    def test_single_day_range_clamped(self):
        metrics = [DayMetrics(timestamp=0, cumulative_loc_delta=5)]
        series = compute_graph_series(metrics)
        assert series.cum_loc_range == 1  # clamped from 0 to 1

    def test_peak_markers(self):
        metrics = [
            DayMetrics(timestamp=0, max_loc_total_7d=10),
            DayMetrics(timestamp=86400, max_loc_total_7d=20),
            DayMetrics(timestamp=172800, max_loc_total_7d=20),
            DayMetrics(timestamp=259200, max_loc_total_7d=25),
        ]
        series = compute_graph_series(metrics)
        assert series.is_new_max7 == [False, True, False, True]


class TestPolylinePoints:
    def test_x_spacing(self):
        from gource_hud.overlay import _precompute_polyline_points
        metrics = [DayMetrics(timestamp=i * 86400, cumulative_loc_delta=i * 10,
                              cumulative_files_delta=0, loc_added_7d=0, loc_deleted_7d=0,
                              max_loc_total_7d=0, max_loc_total_30d=0) for i in range(5)]
        series = compute_graph_series(metrics)
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        pts_loc, _, _, _ = _precompute_polyline_points(series, layout, 5)
        # 5 points, gx1=16, gx2=624, gw=608, step=152
        assert len(pts_loc) == 5
        assert pts_loc[0][0] == 16   # gx1
        assert pts_loc[4][0] == 624  # gx2

    def test_y_normalization(self):
        from gource_hud.overlay import _precompute_polyline_points
        metrics = [
            DayMetrics(timestamp=0, cumulative_loc_delta=0),
            DayMetrics(timestamp=86400, cumulative_loc_delta=50),
            DayMetrics(timestamp=172800, cumulative_loc_delta=100),
        ]
        series = compute_graph_series(metrics)
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        pts_loc, _, _, _ = _precompute_polyline_points(series, layout, 3)
        # value 0 (min) -> gy2 (bottom), value 100 (max) -> gy1 (top)
        gy1 = layout.graph1_bbox[1]
        gy2 = layout.graph1_bbox[3]
        assert pts_loc[0][1] == gy2  # min value -> bottom
        assert pts_loc[2][1] == gy1  # max value -> top (gy2 - graph_h)

    def test_single_day_no_points(self):
        from gource_hud.overlay import _precompute_polyline_points
        metrics = [DayMetrics(timestamp=0, cumulative_loc_delta=42)]
        series = compute_graph_series(metrics)
        layout = compute_layout(1920, 1080, 1.0, 14, 640)
        pts_loc, _, _, _ = _precompute_polyline_points(series, layout, 1)
        assert len(pts_loc) == 1  # single point, no line can be drawn
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_overlay.py -v -k "Formatting or GraphSeries or Polyline"`
Expected: FAIL

- [ ] **Step 3: Implement formatting and graph series**

Add to `gource_hud/overlay.py`:

```python
@dataclass
class GraphSeries:
    cum_loc: list[int] = field(default_factory=list)
    cum_loc_min: int = 0
    cum_loc_range: int = 1
    cum_files: list[int] = field(default_factory=list)
    cum_files_min: int = 0
    cum_files_range: int = 1
    flow_add7: list[int] = field(default_factory=list)
    flow_del7: list[int] = field(default_factory=list)
    flow_max: int = 1
    is_new_max7: list[bool] = field(default_factory=list)
    is_new_max30: list[bool] = field(default_factory=list)


@dataclass
class FormatWidths:
    w_a1: int = 1; w_d1: int = 1; w_n1: int = 1
    w_a7: int = 1; w_d7: int = 1; w_n7: int = 1
    w_a30: int = 1; w_d30: int = 1; w_n30: int = 1
    w_m1: int = 1; w_m7: int = 1; w_m30: int = 1
    w_c1: int = 1; w_c7: int = 1; w_c30: int = 1
    w_u1: int = 1; w_u7: int = 1; w_u30: int = 1
    w_fchg1: int = 1; w_fchg7: int = 1; w_fchg30: int = 1
    w_fadd1: int = 1; w_fadd7: int = 1; w_fadd30: int = 1
    w_fdel1: int = 1; w_fdel7: int = 1; w_fdel30: int = 1
    w_med: int = 1; w_p90: int = 1


def thousands(n: int) -> str:
    return f"{n:,}"


def fmt(n: int, w: int) -> str:
    return thousands(n).rjust(w)


def _maxlen(values: list[int]) -> int:
    return max((len(thousands(v)) for v in values), default=1)


def compute_format_widths(metrics: list[DayMetrics]) -> FormatWidths:
    if not metrics:
        return FormatWidths()
    fw = FormatWidths()
    fw.w_a1 = _maxlen([m.loc_added_1d for m in metrics])
    fw.w_d1 = _maxlen([m.loc_deleted_1d for m in metrics])
    fw.w_n1 = max(fw.w_a1, fw.w_d1) + 1
    fw.w_a7 = _maxlen([m.loc_added_7d for m in metrics])
    fw.w_d7 = _maxlen([m.loc_deleted_7d for m in metrics])
    fw.w_n7 = max(fw.w_a7, fw.w_d7) + 1
    fw.w_a30 = _maxlen([m.loc_added_30d for m in metrics])
    fw.w_d30 = _maxlen([m.loc_deleted_30d for m in metrics])
    fw.w_n30 = max(fw.w_a30, fw.w_d30) + 1
    fw.w_m1 = _maxlen([m.max_loc_total_1d for m in metrics])
    fw.w_m7 = _maxlen([m.max_loc_total_7d for m in metrics])
    fw.w_m30 = _maxlen([m.max_loc_total_30d for m in metrics])
    fw.w_c1 = _maxlen([m.commits_1d for m in metrics])
    fw.w_c7 = _maxlen([m.commits_7d for m in metrics])
    fw.w_c30 = _maxlen([m.commits_30d for m in metrics])
    fw.w_u1 = _maxlen([m.authors_1d for m in metrics])
    fw.w_u7 = _maxlen([m.authors_7d for m in metrics])
    fw.w_u30 = _maxlen([m.authors_30d for m in metrics])
    fw.w_fchg1 = _maxlen([m.files_changed_1d for m in metrics])
    fw.w_fchg7 = _maxlen([m.files_changed_7d for m in metrics])
    fw.w_fchg30 = _maxlen([m.files_changed_30d for m in metrics])
    fw.w_fadd1 = _maxlen([m.files_added_1d for m in metrics])
    fw.w_fadd7 = _maxlen([m.files_added_7d for m in metrics])
    fw.w_fadd30 = _maxlen([m.files_added_30d for m in metrics])
    fw.w_fdel1 = _maxlen([m.files_deleted_1d for m in metrics])
    fw.w_fdel7 = _maxlen([m.files_deleted_7d for m in metrics])
    fw.w_fdel30 = _maxlen([m.files_deleted_30d for m in metrics])
    fw.w_med = _maxlen([m.change_median_7d for m in metrics])
    fw.w_p90 = _maxlen([m.change_p90_7d for m in metrics])
    return fw


def format_day_lines(metrics: list[DayMetrics], widths: FormatWidths) -> list[list[str]]:
    w = widths
    result: list[list[str]] = []
    for m in metrics:
        lg = " ".join(f"{lang} {pct}%" for lang, pct in m.lang_mix_7d) if m.lang_mix_7d else ""
        lines = [
            f"LOC 1d  +{fmt(m.loc_added_1d,w.w_a1)}  -{fmt(m.loc_deleted_1d,w.w_d1)}   (Net {fmt(m.loc_added_1d-m.loc_deleted_1d,w.w_n1)})",
            f"LOC 7d  +{fmt(m.loc_added_7d,w.w_a7)}  -{fmt(m.loc_deleted_7d,w.w_d7)}   (Net {fmt(m.loc_added_7d-m.loc_deleted_7d,w.w_n7)})",
            f"LOC 30d +{fmt(m.loc_added_30d,w.w_a30)}  -{fmt(m.loc_deleted_30d,w.w_d30)}  (Net {fmt(m.loc_added_30d-m.loc_deleted_30d,w.w_n30)})",
            f"Peaks   Max1d {fmt(m.max_loc_total_1d,w.w_m1)}  \u2022  Max7d {fmt(m.max_loc_total_7d,w.w_m7)}  \u2022  Max30d {fmt(m.max_loc_total_30d,w.w_m30)}",
            f"Commits 1d {fmt(m.commits_1d,w.w_c1)}  \u2022  7d {fmt(m.commits_7d,w.w_c7)}  \u2022  30d {fmt(m.commits_30d,w.w_c30)}",
            f"Authors 1d {fmt(m.authors_1d,w.w_u1)}  \u2022  7d {fmt(m.authors_7d,w.w_u7)}  \u2022  30d {fmt(m.authors_30d,w.w_u30)}",
            f"Files\u0394  1d {fmt(m.files_changed_1d,w.w_fchg1)}  \u2022  7d {fmt(m.files_changed_7d,w.w_fchg7)}  \u2022  30d {fmt(m.files_changed_30d,w.w_fchg30)}",
            f"Files A/D  1d +{fmt(m.files_added_1d,w.w_fadd1)}/-{fmt(m.files_deleted_1d,w.w_fdel1)}  \u2022  7d +{fmt(m.files_added_7d,w.w_fadd7)}/-{fmt(m.files_deleted_7d,w.w_fdel7)}  \u2022  30d +{fmt(m.files_added_30d,w.w_fadd30)}/-{fmt(m.files_deleted_30d,w.w_fdel30)}",
            f"Churn 7d {m.churn_7d}%  \u2022  30d {m.churn_30d}%",
            f"Efficiency 7d {m.efficiency_7d}%  \u2022  30d {m.efficiency_30d}%",
            f"Trends 7d  LOC {m.arrow_loc}  \u2022  Commits {m.arrow_commits}  \u2022  Files\u0394 {m.arrow_files}",
            f"Lang 7d  {lg}",
            f"Change Size 7d  median {fmt(m.change_median_7d,w.w_med)}  \u2022  p90 {fmt(m.change_p90_7d,w.w_p90)}",
        ]
        result.append(lines)
    return result


def compute_graph_series(metrics: list[DayMetrics]) -> GraphSeries:
    if not metrics:
        return GraphSeries()

    cum_loc = [m.cumulative_loc_delta for m in metrics]
    cum_files = [m.cumulative_files_delta for m in metrics]
    flow_add7 = [m.loc_added_7d for m in metrics]
    flow_del7 = [m.loc_deleted_7d for m in metrics]

    loc_min = min(cum_loc)
    loc_max = max(cum_loc)
    files_min = min(cum_files)
    files_max = max(cum_files)
    flow_max = max(max(flow_add7, default=0), max(flow_del7, default=0), 1)

    is_new_max7: list[bool] = []
    is_new_max30: list[bool] = []
    prev_max7 = 0
    prev_max30 = 0
    for i, m in enumerate(metrics):
        if i > 0 and m.max_loc_total_7d > prev_max7:
            is_new_max7.append(True)
        else:
            is_new_max7.append(False)
        if i > 0 and m.max_loc_total_30d > prev_max30:
            is_new_max30.append(True)
        else:
            is_new_max30.append(False)
        prev_max7 = m.max_loc_total_7d
        prev_max30 = m.max_loc_total_30d

    return GraphSeries(
        cum_loc=cum_loc,
        cum_loc_min=loc_min,
        cum_loc_range=max(1, loc_max - loc_min),
        cum_files=cum_files,
        cum_files_min=files_min,
        cum_files_range=max(1, files_max - files_min),
        flow_add7=flow_add7,
        flow_del7=flow_del7,
        flow_max=flow_max,
        is_new_max7=is_new_max7,
        is_new_max30=is_new_max30,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_overlay.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/overlay.py tests/test_overlay.py
git commit -m "feat(overlay): add text formatting, format widths, and graph series precomputation"
```

---

### Task 15: Font loading and frame rendering

**Files:**
- Modify: `gource_hud/overlay.py`
- Modify: `tests/test_overlay.py`

- [ ] **Step 1: Write tests for font loading and render_overlays**

Append to `tests/test_overlay.py`:

```python
import tempfile
from unittest.mock import patch
from gource_hud.overlay import find_mono_font, render_overlays


class TestFindMonoFont:
    def test_finds_system_font(self):
        # May skip on systems without fonts
        try:
            path = find_mono_font()
            assert os.path.isfile(path)
        except RuntimeError:
            import pytest
            pytest.skip("No system monospaced font found")

    def test_raises_when_no_font(self):
        import pytest
        with patch("os.path.isfile", return_value=False):
            with pytest.raises(RuntimeError, match="No monospaced font"):
                find_mono_font()


class TestRenderOverlays:
    def test_empty_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            count = render_overlays([], tmpdir, 1920, 1080)
            assert count == 0

    def test_single_frame_output(self):
        m = DayMetrics(timestamp=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            count = render_overlays([m], tmpdir, 1920, 1080, jobs=1)
            assert count == 1
            out_path = os.path.join(tmpdir, "overlay_00000.png")
            assert os.path.exists(out_path)
            im = Image.open(out_path)
            assert im.mode == "RGBA"
            assert im.size == (1920, 1080)

    def test_panel_not_transparent(self):
        m = DayMetrics(timestamp=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            render_overlays([m], tmpdir, 1920, 1080, jobs=1)
            im = Image.open(os.path.join(tmpdir, "overlay_00000.png"))
            # Sample pixel inside panel area (bottom-left)
            pixel = im.getpixel((100, 1000))
            assert pixel[3] > 0  # non-transparent

    def test_outside_panel_transparent(self):
        m = DayMetrics(timestamp=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            render_overlays([m], tmpdir, 1920, 1080, jobs=1)
            im = Image.open(os.path.join(tmpdir, "overlay_00000.png"))
            pixel = im.getpixel((1900, 10))  # top-right corner
            assert pixel[3] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_overlay.py -v -k "Font or RenderOverlay"`
Expected: FAIL — cannot import `find_mono_font`, `render_overlays`

- [ ] **Step 3: Implement font loading and render_overlays**

Add to `gource_hud/overlay.py`:

```python
MONO_FONT_SEARCH_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/Library/Fonts/Courier New.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
]


def find_mono_font() -> str:
    for path in MONO_FONT_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    raise RuntimeError(
        "No monospaced font found. Install dejavu-sans-mono or pass --font-file."
    )


def _precompute_polyline_points(
    series: GraphSeries,
    layout: LayoutMetrics,
    n_days: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    gx1, _, gx2, _ = layout.graph1_bbox
    gw = max(1, gx2 - gx1)
    step = gw / max(1, n_days - 1) if n_days > 1 else 0

    def make_points(values: list[int], val_min: int, val_range: int, bbox: tuple[int, int, int, int]) -> list[tuple[int, int]]:
        _, gy1, _, gy2 = bbox
        pts: list[tuple[int, int]] = []
        for j in range(n_days):
            x = int(round(gx1 + j * step))
            norm = (values[j] - val_min) / val_range if val_range > 0 else 0
            y = int(round(gy2 - norm * layout.graph_h))
            pts.append((x, y))
        return pts

    pts_loc = make_points(series.cum_loc, series.cum_loc_min, series.cum_loc_range, layout.graph1_bbox)
    pts_files = make_points(series.cum_files, series.cum_files_min, series.cum_files_range, layout.graph2_bbox)
    pts_add7 = make_points(series.flow_add7, 0, series.flow_max, layout.graph3_bbox)
    pts_del7 = make_points(series.flow_del7, 0, series.flow_max, layout.graph3_bbox)

    return pts_loc, pts_files, pts_add7, pts_del7


def _render_frame(
    frame_index: int,
    day_lines: list[str],
    layout: LayoutMetrics,
    series: GraphSeries,
    pts_loc: list[tuple[int, int]],
    pts_files: list[tuple[int, int]],
    pts_add7: list[tuple[int, int]],
    pts_del7: list[tuple[int, int]],
    font_path: str,
    frame_w: int,
    frame_h: int,
    output_path: str,
) -> None:
    font = ImageFont.truetype(font_path, layout.font_size)
    im = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    # Panel background
    draw.rectangle(
        [layout.rect_x1, layout.rect_y1, layout.rect_x2, layout.rect_y2],
        fill=(0, 0, 0, 140),
    )

    # Graph borders
    border_color = (255, 255, 255, 102)
    for bbox in [layout.graph1_bbox, layout.graph2_bbox, layout.graph3_bbox]:
        draw.rectangle(list(bbox), fill=None, outline=border_color, width=1)

    # Text lines
    y = layout.text_y_start
    for line in day_lines:
        draw.text(
            (layout.text_x, y), line,
            fill=(255, 255, 255, 255),
            font=font,
            stroke_width=layout.stroke_width,
            stroke_fill=(0, 0, 0, 153),
        )
        y += layout.line_gap

    # Graph labels
    labels = [
        ("Total LOC (\u0394)", layout.graph1_bbox),
        ("Files (\u0394)", layout.graph2_bbox),
        ("+Adds / -Deletes (7d)", layout.graph3_bbox),
    ]
    for label, (gx1, gy1, _, _) in labels:
        draw.text(
            (gx1 + 2, gy1 + 2), label,
            fill=(255, 255, 255, 255),
            font=font,
            stroke_width=layout.stroke_width,
            stroke_fill=(0, 0, 0, 153),
        )

    # Polylines
    if frame_index >= 1:
        pts = pts_loc[: frame_index + 1]
        if len(pts) >= 2:
            draw.line(pts, fill=(255, 255, 255), width=layout.polyline_width)
        pts = pts_files[: frame_index + 1]
        if len(pts) >= 2:
            draw.line(pts, fill=(0, 255, 255), width=layout.polyline_width)
        pts = pts_add7[: frame_index + 1]
        if len(pts) >= 2:
            draw.line(pts, fill=(0, 255, 102), width=layout.polyline_width)
        pts = pts_del7[: frame_index + 1]
        if len(pts) >= 2:
            draw.line(pts, fill=(255, 85, 85), width=layout.polyline_width)

    # Peak markers
    if frame_index > 0:
        gx1 = layout.graph1_bbox[0]
        gx2 = layout.graph1_bbox[2]
        gw = max(1, gx2 - gx1)
        n = len(series.cum_loc)
        step = gw / max(1, n - 1) if n > 1 else 0
        cx = int(round(gx1 + frame_index * step))
        r = max(2, int(2 * layout.scale))
        if series.is_new_max7[frame_index]:
            cy = layout.graph1_bbox[1] + int(6 * layout.scale)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 215, 0))
        if series.is_new_max30[frame_index]:
            cy = layout.graph1_bbox[1] + int(14 * layout.scale)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 0, 255))

    im.save(output_path, format="PNG")


def render_overlays(
    day_data: list[DayMetrics],
    output_dir: str,
    width: int,
    height: int,
    font_path: str | None = None,
    panel_width: int = 640,
    font_size: int = 14,
    jobs: int = 0,
    scale: float = 1.0,
) -> int:
    if not day_data:
        return 0

    if font_path is None:
        font_path = find_mono_font()
    elif not os.path.isfile(font_path):
        raise FileNotFoundError(f"Font file not found: {font_path}")

    layout = compute_layout(width, height, scale, font_size, panel_width)
    series = compute_graph_series(day_data)
    widths = compute_format_widths(day_data)
    all_lines = format_day_lines(day_data, widths)
    pts_loc, pts_files, pts_add7, pts_del7 = _precompute_polyline_points(
        series, layout, len(day_data)
    )

    total = len(day_data)
    if jobs <= 0:
        jobs = max(1, min(16, (os.cpu_count() or 2) * 4))

    def render_one(i: int) -> None:
        out = os.path.join(output_dir, f"overlay_{i:05d}.png")
        _render_frame(
            i, all_lines[i], layout, series,
            pts_loc, pts_files, pts_add7, pts_del7,
            font_path, width, height, out,
        )

    done = 0
    step = max(1, total // 20)
    sys.stderr.write(f"[HUD] Rendering overlays: 0/{total} frames using {jobs} workers\n")
    sys.stderr.flush()

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {executor.submit(render_one, i): i for i in range(total)}
        failed: list[int] = []
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception:
                failed.append(futures[fut])
            done += 1
            if done == 1 or done % step == 0 or done == total:
                sys.stderr.write(f"[HUD] Rendering overlays: {done}/{total}\r")
                sys.stderr.flush()
    sys.stderr.write("\n")
    sys.stderr.flush()

    # Retry failed frames sequentially
    if failed:
        sys.stderr.write(f"[HUD] Retrying {len(failed)} failed frames\n")
        still_failed: list[int] = []
        for i in failed:
            try:
                render_one(i)
            except Exception:
                still_failed.append(i)
        if still_failed:
            raise RuntimeError(f"Failed to render overlay frames: {still_failed}")

    return total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_overlay.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/overlay.py tests/test_overlay.py
git commit -m "feat(overlay): add font loading, frame rendering, and render_overlays"
```

---

## Chunk 4: video.py + cli.py

### Task 16: Video pipeline — command builders and dependency check

**Files:**
- Create: `gource_hud/video.py`
- Create: `tests/test_video.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_video.py
import shutil
from pathlib import Path
from unittest.mock import patch

from gource_hud.video import (
    VideoConfig, DependencyError, RenderError,
    check_dependencies, _build_gource_cmd, _build_ffmpeg_cmd,
    _count_overlay_frames,
)


class TestVideoConfig:
    def test_defaults(self):
        c = VideoConfig(
            log_file=Path("/tmp/log"),
            overlay_dir=Path("/tmp/ovr"),
            output_path=Path("/tmp/out.mp4"),
        )
        assert c.fps == 60
        assert c.seconds_per_day == 0.5
        assert c.crf == 18


class TestCheckDependencies:
    def test_raises_when_gource_missing(self):
        import pytest
        with patch("shutil.which", side_effect=lambda t: None if t == "gource" else "/usr/bin/ffmpeg"):
            with pytest.raises(DependencyError, match="gource"):
                check_dependencies()

    def test_raises_when_ffmpeg_missing(self):
        import pytest
        with patch("shutil.which", side_effect=lambda t: None if t == "ffmpeg" else "/usr/bin/gource"):
            with pytest.raises(DependencyError, match="ffmpeg"):
                check_dependencies()


class TestBuildGourceCmd:
    def test_default_config(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"))
        cmd = _build_gource_cmd(c)
        assert "gource" == cmd[0]
        assert "--log-format" in cmd
        assert "--output-ppm-stream" in cmd
        assert "-1920x1080" in cmd
        assert "--auto-skip-seconds" not in " ".join(cmd)

    def test_uhd_config(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"),
                       width=3840, height=2160)
        cmd = _build_gource_cmd(c)
        assert "-3840x2160" in cmd


class TestBuildFfmpegCmd:
    def test_overlay_fps(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"),
                       seconds_per_day=0.5)
        cmd = _build_ffmpeg_cmd(c, overlay_fps=2.0)
        cmd_str = " ".join(cmd)
        assert "-framerate" in cmd_str
        assert "2.0" in cmd_str

    def test_filter_complex_content(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"),
                       fps=60, tail_pause=4.0)
        cmd = _build_ffmpeg_cmd(c, overlay_fps=2.0)
        fc_idx = cmd.index("-filter_complex") + 1
        fc = cmd[fc_idx]
        assert "fps=60" in fc
        assert "overlay=x=0:y=0:format=auto" in fc
        assert "tpad=stop_mode=clone:stop_duration=4.0" in fc

    def test_crf_value(self):
        c = VideoConfig(Path("/tmp/log"), Path("/tmp/ovr"), Path("/tmp/out.mp4"), crf=22)
        cmd = _build_ffmpeg_cmd(c, overlay_fps=2.0)
        assert "22" in cmd


class TestCountOverlayFrames:
    def test_counts_correctly(self, tmp_path):
        for i in range(5):
            (tmp_path / f"overlay_{i:05d}.png").touch()
        (tmp_path / "other.txt").touch()  # should be ignored
        assert _count_overlay_frames(tmp_path) == 5

    def test_empty_dir(self, tmp_path):
        assert _count_overlay_frames(tmp_path) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_video.py -v`
Expected: FAIL — cannot import from `gource_hud.video`

- [ ] **Step 3: Implement video module**

```python
# gource_hud/video.py
from __future__ import annotations

import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


class DependencyError(RuntimeError):
    pass


class RenderError(RuntimeError):
    pass


@dataclass
class VideoConfig:
    log_file: Path
    overlay_dir: Path
    output_path: Path
    width: int = 1920
    height: int = 1080
    fps: int = 60
    seconds_per_day: float = 0.5
    title: str = "Repository Activity"
    tail_pause: float = 4.0
    crf: int = 18


def check_dependencies() -> None:
    for tool in ("gource", "ffmpeg"):
        if shutil.which(tool) is None:
            raise DependencyError(
                f"'{tool}' not found on PATH. Install it: sudo apt-get install {tool}"
            )


def _build_gource_cmd(config: VideoConfig) -> list[str]:
    return [
        "gource",
        "--log-format", "custom",
        str(config.log_file),
        "--hide", "usernames,filenames,dirnames",
        "--seconds-per-day", str(config.seconds_per_day),
        "--camera-mode", "overview",
        "--stop-at-end",
        "--title", config.title,
        f"-{config.width}x{config.height}",
        "--output-ppm-stream", "-",
    ]


def _build_ffmpeg_cmd(config: VideoConfig, overlay_fps: float) -> list[str]:
    fps = config.fps
    filter_complex = (
        f"[0:v]fps={fps},settb=AVTB,setpts=N/({fps}*TB)[bg];"
        f"[1:v]fps={fps},format=rgba,settb=AVTB,setpts=N/({fps}*TB)[ov];"
        f"[bg][ov]overlay=x=0:y=0:format=auto,"
        f"tpad=stop_mode=clone:stop_duration={config.tail_pause}"
    )
    return [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-r", str(fps),
        "-f", "image2pipe", "-vcodec", "ppm",
        "-i", "-",
        "-framerate", str(overlay_fps),
        "-start_number", "0",
        "-i", str(config.overlay_dir / "overlay_%05d.png"),
        "-filter_complex", filter_complex,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-crf", str(config.crf),
        str(config.output_path),
    ]


def _count_overlay_frames(overlay_dir: Path) -> int:
    return len(list(overlay_dir.glob("overlay_*.png")))


def render_video(config: VideoConfig) -> Path:
    check_dependencies()

    if not config.log_file.exists():
        raise FileNotFoundError(f"Log file not found: {config.log_file}")
    if not config.overlay_dir.is_dir():
        raise FileNotFoundError(f"Overlay directory not found: {config.overlay_dir}")

    frame_count = _count_overlay_frames(config.overlay_dir)
    if frame_count == 0:
        raise FileNotFoundError(f"No overlay_*.png files in {config.overlay_dir}")

    config.output_path.parent.mkdir(parents=True, exist_ok=True)

    overlay_fps = 1.0 / config.seconds_per_day
    gource_cmd = _build_gource_cmd(config)
    ffmpeg_cmd = _build_ffmpeg_cmd(config, overlay_fps)

    gource_proc: subprocess.Popen | None = None
    ffmpeg_proc: subprocess.Popen | None = None

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)

    def _cleanup_handler(signum: int, frame: object) -> None:
        for proc in (gource_proc, ffmpeg_proc):
            if proc and proc.poll() is None:
                proc.terminate()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    try:
        signal.signal(signal.SIGINT, _cleanup_handler)
        signal.signal(signal.SIGTERM, _cleanup_handler)

        gource_proc = subprocess.Popen(
            gource_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=gource_proc.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # Close gource stdout in parent so ffmpeg sees EOF
        gource_proc.stdout.close()  # type: ignore[union-attr]

        ffmpeg_stderr_lines: list[str] = []
        for line in ffmpeg_proc.stderr:  # type: ignore[union-attr]
            decoded = line.decode("utf-8", errors="replace").rstrip()
            ffmpeg_stderr_lines.append(decoded)

        ffmpeg_rc = ffmpeg_proc.wait()
        gource_rc = gource_proc.wait()

        gource_stderr = gource_proc.stderr.read().decode("utf-8", errors="replace")  # type: ignore[union-attr]

        if gource_rc != 0:
            raise RenderError(f"gource failed (exit {gource_rc}):\n{gource_stderr}")
        if ffmpeg_rc != 0:
            raise RenderError(
                f"ffmpeg failed (exit {ffmpeg_rc}):\n" + "\n".join(ffmpeg_stderr_lines[-20:])
            )
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)
        for proc in (gource_proc, ffmpeg_proc):
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()

    return config.output_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_video.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add gource_hud/video.py tests/test_video.py
git commit -m "feat(video): add VideoConfig, command builders, dependency check, and render_video"
```

---

### Task 17: CLI entry point

**Files:**
- Create: `gource_hud/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write tests for CLI argument parsing**

```python
# tests/test_cli.py
import sys
from unittest.mock import patch
from gource_hud.cli import parse_args


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.repo is None
        assert args.output is None
        assert args.no_anon is False
        assert args.speed == 0.5
        assert args.fps == 60
        assert args.window == "4 months ago"
        assert args.uhd is False

    def test_repo_path(self):
        args = parse_args(["/some/repo"])
        assert args.repo == "/some/repo"

    def test_repo_and_output(self):
        args = parse_args(["/some/repo", "out.mp4"])
        assert args.repo == "/some/repo"
        assert args.output == "out.mp4"

    def test_uhd_flag(self):
        args = parse_args(["--uhd"])
        assert args.uhd is True

    def test_4k_alias(self):
        args = parse_args(["--4k"])
        assert args.uhd is True

    def test_fhd_no_op(self):
        args = parse_args(["--fhd"])
        assert args.uhd is False

    def test_no_anon(self):
        args = parse_args(["--no-anon"])
        assert args.no_anon is True

    def test_tunables(self):
        args = parse_args(["--speed", "0.3", "--fps", "30", "--crf", "22"])
        assert args.speed == 0.3
        assert args.fps == 30
        assert args.crf == 22
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — cannot import `parse_args`

- [ ] **Step 3: Implement CLI**

```python
# gource_hud/cli.py
from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from gource_hud.git_log import Anonymizer, parse_git_log, write_gource_log
from gource_hud.overlay import render_overlays
from gource_hud.stats import compute_all_metrics
from gource_hud.video import VideoConfig, check_dependencies, render_video


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="gource-hud",
        description="Generate a gource visualization with a rich HUD overlay.",
    )
    p.add_argument("repo", nargs="?", default=None, help="Git repo path (default: cwd)")
    p.add_argument("output", nargs="?", default=None, help="Output .mp4 path")

    res = p.add_argument_group("resolution")
    res.add_argument("--uhd", "--4k", action="store_true", default=False, help="3840x2160")
    res.add_argument("--fhd", action="store_true", default=False, help="1920x1080 (default, no-op)")

    p.add_argument("--no-anon", action="store_true", default=False, help="Show real names/paths")

    tun = p.add_argument_group("tunables")
    tun.add_argument("--window", default="4 months ago", help="Git log time window")
    tun.add_argument("--speed", type=float, default=0.5, help="Seconds per simulated day")
    tun.add_argument("--fps", type=int, default=60)
    tun.add_argument("--title", default="Repository Activity")
    tun.add_argument("--tail-pause", type=float, default=4.0)
    tun.add_argument("--crf", type=int, default=18)

    hud = p.add_argument_group("HUD appearance")
    hud.add_argument("--font-file", default=None)
    hud.add_argument("--font-size", type=int, default=14)
    hud.add_argument("--panel-width", type=int, default=640)

    p.add_argument("--jobs", type=int, default=0)

    return p.parse_args(argv)


def main() -> None:
    args = parse_args()

    repo_path = args.repo or "."
    repo = Path(repo_path).resolve()
    if not (repo / ".git").is_dir():
        print(f"Not a git repo: {repo}", file=sys.stderr)
        sys.exit(1)

    width = 3840 if args.uhd else 1920
    height = 2160 if args.uhd else 1080
    scale = 2.0 if args.uhd else 1.0

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = repo / f"gource_anon_{width}x{height}_{ts}.mp4"

    check_dependencies()

    with tempfile.TemporaryDirectory(prefix="gource_hud_") as tmpdir:
        tmp = Path(tmpdir)

        print("Parsing git log...", file=sys.stderr)
        commits = parse_git_log(str(repo), args.window)
        if not commits:
            print("No commits found in the given time window.", file=sys.stderr)
            sys.exit(1)

        if not args.no_anon:
            print("Anonymizing...", file=sys.stderr)
            anonymizer = Anonymizer()
            commits = anonymizer.anonymize_commits(commits)

        log_file = tmp / "repo.anon.log"
        write_gource_log(commits, log_file)

        print("Computing stats...", file=sys.stderr)
        metrics = compute_all_metrics(commits)

        print("Rendering overlays...", file=sys.stderr)
        render_overlays(
            metrics, str(tmp), width, height,
            font_path=args.font_file,
            panel_width=args.panel_width,
            font_size=args.font_size,
            jobs=args.jobs,
            scale=scale,
        )

        print("Rendering video...", file=sys.stderr)
        config = VideoConfig(
            log_file=log_file,
            overlay_dir=tmp,
            output_path=output_path,
            width=width,
            height=height,
            fps=args.fps,
            seconds_per_day=args.speed,
            title=args.title,
            tail_pause=args.tail_pause,
            crf=args.crf,
        )
        render_video(config)

    print(f"Wrote: {output_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: All pass

- [ ] **Step 5: Verify entry point works**

Run: `gource-hud --help`
Expected: Usage message printed with all documented flags.

- [ ] **Step 6: Commit**

```bash
git add gource_hud/cli.py tests/test_cli.py
git commit -m "feat(cli): add argument parsing and main entry point"
```

---

### Task 18: Run full test suite

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Verify editable install still works**

Run: `pip install -e ".[dev]" && gource-hud --help`
Expected: Installs cleanly, help message prints

- [ ] **Step 3: Final commit if any cleanup needed**

```bash
git add -A
git status  # verify no unintended files
git commit -m "chore: final test suite verification"
```
