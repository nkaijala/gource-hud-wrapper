from gource_hud.stats import DayBucket, bucket_commits
from gource_hud.git_log import Commit, FileChange, FileStatus

DAY = 86400


class TestBucketCommits:
    def test_single_commit(self):
        commits = [Commit(DAY * 10, "a" * 40, "alice", [FileChange("a.py", FileStatus.MODIFIED, 10, 2, False)])]
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
            Commit(DAY * 0, "a" * 40, "alice", [FileChange("a.py", FileStatus.ADDED, 20, 0, False)]),
            Commit(DAY * 3, "b" * 40, "bob", [FileChange("b.py", FileStatus.ADDED, 10, 0, False)]),
        ]
        days, buckets = bucket_commits(commits)
        assert len(days) == 4
        assert buckets[DAY * 1].commit_count == 0
        assert buckets[DAY * 1].authors == set()
        assert buckets[DAY * 2].loc_added == 0

    def test_multiple_commits_same_day(self):
        commits = [
            Commit(DAY * 5, "a" * 40, "alice", [FileChange("a.py", FileStatus.MODIFIED, 10, 0, False)]),
            Commit(DAY * 5 + 3600, "b" * 40, "bob", [FileChange("b.py", FileStatus.ADDED, 5, 0, False)]),
        ]
        days, buckets = bucket_commits(commits)
        assert len(days) == 1
        b = buckets[DAY * 5]
        assert b.commit_count == 2
        assert b.authors == {"alice", "bob"}
        assert b.loc_added == 15
        assert b.files_added_count == 1

    def test_files_added_deleted(self):
        commits = [Commit(DAY * 0, "a" * 40, "dev", [
            FileChange("new.py", FileStatus.ADDED, 10, 0, False),
            FileChange("old.py", FileStatus.DELETED, 0, 8, False),
        ])]
        days, buckets = bucket_commits(commits)
        b = buckets[DAY * 0]
        assert b.files_added_count == 1
        assert b.files_deleted_count == 1

    def test_empty_input(self):
        days, buckets = bucket_commits([])
        assert days == []
        assert buckets == {}
