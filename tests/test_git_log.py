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
    c = Commit(timestamp=1700000000, hash="a" * 40, author_email="dev@example.com", files=[])
    expected_day = (1700000000 // 86400) * 86400
    assert c.day_epoch == expected_day

def test_file_change_defaults():
    fc = FileChange(path="src/main.py", status=FileStatus.MODIFIED, adds=10, deletes=3, is_binary=False)
    assert fc.old_path is None
    assert fc.rename_score is None
