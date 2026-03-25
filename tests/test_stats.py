from gource_hud.stats import (
    DayBucket, bucket_commits, rolling_sum, rolling_unique_count,
    running_maxima, cumulative_series, percentile,
)
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
        assert result[DAY * 6] == 100
        assert result[DAY * 7] == 0

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
        days = [DAY * i for i in range(8)]
        sets = {d: set() for d in days}
        sets[DAY * 0] = {"alice"}
        sets[DAY * 1] = {"bob"}
        sets[DAY * 7] = {"carol"}
        result = rolling_unique_count(days, sets, 7 * DAY)
        assert result[DAY * 6] == 2
        assert result[DAY * 7] == 2

    def test_partial_eviction(self):
        days = [DAY * i for i in range(8)]
        sets = {d: set() for d in days}
        sets[DAY * 0] = {"alice"}
        sets[DAY * 2] = {"alice"}
        result = rolling_unique_count(days, sets, 7 * DAY)
        assert result[DAY * 7] == 1

    def test_empty(self):
        assert rolling_unique_count([], {}, DAY) == {}


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
        assert percentile([1, 2, 3, 4, 5], 0.9) == 5

    def test_six_values(self):
        assert percentile([1, 3, 5, 7, 9, 11], 0.5) == 6
        assert percentile([1, 3, 5, 7, 9, 11], 0.9) == 10
