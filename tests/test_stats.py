from gource_hud.stats import (
    DayBucket, bucket_commits, rolling_sum, rolling_unique_count,
    running_maxima, cumulative_series, percentile,
    compute_churn, compute_efficiency, compute_wow_delta,
    format_trend_arrow, lang_from_path, EXTENSION_TO_LANGUAGE,
    compute_language_mix_7d, compute_change_size_distribution_7d,
    DayMetrics, compute_all_metrics,
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
        assert compute_churn(1, 2) == 67

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
        assert compute_wow_delta(values, 7) == 70

    def test_wow_delta_insufficient_history(self):
        values = [10, 20, 30]
        assert compute_wow_delta(values, 2) == 0

    def test_format_arrow_positive(self):
        assert format_trend_arrow(5) == "\u25b2 +5"

    def test_format_arrow_negative(self):
        assert format_trend_arrow(-3) == "\u25bc 3"

    def test_format_arrow_zero(self):
        assert format_trend_arrow(0) == "\u2013 0"


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
        lang_loc = {d: {} for d in days}
        lang_loc[DAY * 0] = {"python": 1000}
        lang_loc[DAY * 7] = {"go": 100}
        result = compute_language_mix_7d(days, lang_loc)
        assert result[DAY * 7] == [("go", 100)]

    def test_empty_window(self):
        days = [DAY * 0]
        lang_loc = {DAY * 0: {}}
        result = compute_language_mix_7d(days, lang_loc)
        assert result[DAY * 0] == []


class TestChangeSizeDistribution7d:
    def test_basic(self):
        days = [DAY * 0]
        sizes = {DAY * 0: [10, 30, 50]}
        result = compute_change_size_distribution_7d(days, sizes)
        assert result[DAY * 0] == (30, 46)

    def test_empty_window(self):
        days = [DAY * 0]
        sizes = {DAY * 0: []}
        result = compute_change_size_distribution_7d(days, sizes)
        assert result[DAY * 0] == (0, 0)

    def test_eviction(self):
        days = [DAY * i for i in range(8)]
        sizes = {d: [] for d in days}
        sizes[DAY * 0] = [1000]
        sizes[DAY * 7] = [10]
        result = compute_change_size_distribution_7d(days, sizes)
        assert result[DAY * 7] == (10, 10)


class TestComputeAllMetrics:
    def test_empty_input(self):
        assert compute_all_metrics([]) == []

    def test_single_day(self):
        commits = [Commit(DAY * 10, "a" * 40, "alice", [FileChange("main.py", FileStatus.MODIFIED, 42, 7, False)])]
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
        assert m.cumulative_files_delta == 0

    def test_three_days(self):
        commits = [
            Commit(DAY * 10, "a" * 40, "alice", [FileChange("a.py", FileStatus.MODIFIED, 10, 2, False)]),
            Commit(DAY * 11, "b" * 40, "alice", [FileChange("b.py", FileStatus.ADDED, 5, 0, False)]),
            Commit(DAY * 12, "c" * 40, "alice", [FileChange("a.py", FileStatus.MODIFIED, 3, 1, False)]),
        ]
        result = compute_all_metrics(commits)
        assert len(result) == 3
        m = result[2]
        assert m.loc_added_7d == 18
        assert m.loc_deleted_7d == 3
        assert m.commits_7d == 3
        assert m.cumulative_loc_delta == 15
        assert m.cumulative_files_delta == 1

    def test_has_derived_metrics(self):
        commits = [Commit(DAY * 10, "a" * 40, "alice", [FileChange("a.py", FileStatus.MODIFIED, 80, 20, False)])]
        result = compute_all_metrics(commits)
        m = result[0]
        assert m.churn_7d == 20
        assert m.efficiency_7d == 60
        assert m.arrow_loc == "\u2013 0"
