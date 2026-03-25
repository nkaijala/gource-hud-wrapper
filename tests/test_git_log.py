# tests/test_git_log.py
from gource_hud.git_log import FileStatus, FileChange, Commit, _parse_numstat_output, _resolve_numstat_path

def test_file_status_values():
    assert FileStatus.ADDED.value == "A"
    assert FileStatus.MODIFIED.value == "M"
    assert FileStatus.DELETED.value == "D"
    assert FileStatus.TYPE_CHANGED.value == "T"
    assert FileStatus.RENAMED.value == "R"
    assert FileStatus.COPIED.value == "C"

def test_commit_day_epoch():
    c = Commit(timestamp=1700000000, hash="a" * 40, author_email="dev@example.com", files=[])
    expected_day = (1700000000 // 86400) * 86400
    assert c.day_epoch == expected_day

def test_file_change_defaults():
    fc = FileChange(path="src/main.py", status=FileStatus.MODIFIED, adds=10, deletes=3, is_binary=False)
    assert fc.old_path is None
    assert fc.rename_score is None


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
        assert _resolve_numstat_path("{ => subdir}/file.py") == "subdir/file.py"
    def test_brace_empty_new(self):
        assert _resolve_numstat_path("{subdir => }/file.py") == "file.py"


class TestParseNumstatOutput:
    def test_single_commit_two_files(self):
        raw = "1700000000\t" + "a" * 40 + "\tdev@example.com\n\n10\t3\tsrc/main.py\n5\t0\tsrc/utils.py\n"
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
        raw = "1700000000\t" + "b" * 40 + "\tdev@example.com\n\n-\t-\timage.png\n"
        commits = _parse_numstat_output(raw)
        assert commits[0].file_stats[0] == (0, 0, "image.png", True)
    def test_multiple_commits(self):
        raw = "1700000000\t" + "a" * 40 + "\talice@x.com\n\n1\t0\ta.py\n\n1700086400\t" + "b" * 40 + "\tbob@x.com\n\n2\t1\tb.py\n"
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
        raw = "1700000000\t" + "d" * 40 + "\tdev@x.com\n\n0\t0\tsrc/{old => new}/file.py\n"
        commits = _parse_numstat_output(raw)
        assert commits[0].file_stats[0][2] == "src/new/file.py"
    def test_path_with_spaces(self):
        raw = "1700000000\t" + "e" * 40 + "\tdev@x.com\n\n3\t1\tsrc/my file.py\n"
        commits = _parse_numstat_output(raw)
        assert commits[0].file_stats[0][2] == "src/my file.py"
