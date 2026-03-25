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


def rolling_sum(days: list[int], values: dict[int, int], window_seconds: int) -> dict[int, int]:
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


def rolling_unique_count(days: list[int], sets_by_day: dict[int, set[str]], window_seconds: int) -> dict[int, int]:
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
        return f"\u25b2 +{delta}"
    elif delta < 0:
        return f"\u25bc {abs(delta)}"
    return "\u2013 0"


EXTENSION_TO_LANGUAGE: dict[str, str] = {
    "py": "python", "pyi": "python", "pyx": "python", "ipynb": "python",
    "ts": "typescript", "tsx": "typescript", "mts": "typescript", "cts": "typescript",
    "js": "javascript", "jsx": "javascript", "mjs": "javascript", "cjs": "javascript",
    "go": "go", "rs": "rust", "java": "java",
    "kt": "kotlin", "kts": "kotlin",
    "rb": "ruby", "rake": "ruby", "gemspec": "ruby",
    "php": "php",
    "c": "c", "h": "c",
    "cc": "c++", "cpp": "c++", "cxx": "c++", "hh": "c++", "hpp": "c++", "hxx": "c++",
    "cs": "c#", "swift": "swift",
    "m": "obj-c", "mm": "obj-c",
    "sh": "shell", "bash": "shell", "zsh": "shell", "fish": "shell",
    "yml": "yaml", "yaml": "yaml",
    "json": "json", "toml": "toml",
    "md": "markdown", "mdx": "markdown",
    "sql": "sql", "r": "r", "jl": "julia",
    "scala": "scala", "sc": "scala",
}


def lang_from_path(path: str) -> str:
    filename = path.rsplit("/", 1)[-1]
    if "." not in filename:
        return "other"
    ext = filename.rsplit(".", 1)[-1].lower()
    return EXTENSION_TO_LANGUAGE.get(ext, "other")


def compute_language_mix_7d(
    days: list[int], lang_loc_day: dict[int, dict[str, int]]
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
    days: list[int], sizes_on_day: dict[int, list[int]]
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


# Window constants
W1 = DAY_SECONDS
W7 = 7 * DAY_SECONDS
W30 = 30 * DAY_SECONDS


@dataclass
class DayMetrics:
    timestamp: int
    # LOC
    loc_added_1d: int = 0
    loc_added_7d: int = 0
    loc_added_30d: int = 0
    loc_deleted_1d: int = 0
    loc_deleted_7d: int = 0
    loc_deleted_30d: int = 0
    # Commits
    commits_1d: int = 0
    commits_7d: int = 0
    commits_30d: int = 0
    # Authors
    authors_1d: int = 0
    authors_7d: int = 0
    authors_30d: int = 0
    # Files changed
    files_changed_1d: int = 0
    files_changed_7d: int = 0
    files_changed_30d: int = 0
    # Files added/deleted
    files_added_1d: int = 0
    files_added_7d: int = 0
    files_added_30d: int = 0
    files_deleted_1d: int = 0
    files_deleted_7d: int = 0
    files_deleted_30d: int = 0
    # Max LOC total (adds+deletes)
    max_loc_total_1d: int = 0
    max_loc_total_7d: int = 0
    max_loc_total_30d: int = 0
    # Cumulative
    cumulative_loc_delta: int = 0
    cumulative_files_delta: int = 0
    # Churn and efficiency
    churn_7d: int = 0
    churn_30d: int = 0
    efficiency_7d: int = 0
    efficiency_30d: int = 0
    # WoW deltas
    delta_loc_7d: int = 0
    delta_commits_7d: int = 0
    delta_files_7d: int = 0
    # Trend arrows
    arrow_loc: str = ""
    arrow_commits: str = ""
    arrow_files: str = ""
    # Language mix
    lang_mix_7d: list[tuple[str, int]] = field(default_factory=list)
    # Change size distribution
    change_median_7d: int = 0
    change_p90_7d: int = 0


def compute_all_metrics(commits: list[Commit]) -> list[DayMetrics]:
    if not commits:
        return []

    days, buckets = bucket_commits(commits)
    if not days:
        return []

    # Extract per-day scalar values from buckets
    loc_added_day = {t: buckets[t].loc_added for t in days}
    loc_deleted_day = {t: buckets[t].loc_deleted for t in days}
    commit_count_day = {t: buckets[t].commit_count for t in days}
    files_changed_day = {t: buckets[t].files_changed for t in days}
    authors_day = {t: buckets[t].authors for t in days}
    files_added_day = {t: buckets[t].files_added_count for t in days}
    files_deleted_day = {t: buckets[t].files_deleted_count for t in days}
    loc_total_day = {t: buckets[t].loc_added + buckets[t].loc_deleted for t in days}
    loc_delta_day = {t: buckets[t].loc_added - buckets[t].loc_deleted for t in days}
    files_delta_day = {t: buckets[t].files_added_count - buckets[t].files_deleted_count for t in days}

    # Rolling sums for 1d, 7d, 30d
    loc_added_1d = rolling_sum(days, loc_added_day, W1)
    loc_added_7d = rolling_sum(days, loc_added_day, W7)
    loc_added_30d = rolling_sum(days, loc_added_day, W30)
    loc_deleted_1d = rolling_sum(days, loc_deleted_day, W1)
    loc_deleted_7d = rolling_sum(days, loc_deleted_day, W7)
    loc_deleted_30d = rolling_sum(days, loc_deleted_day, W30)
    commits_1d = rolling_sum(days, commit_count_day, W1)
    commits_7d = rolling_sum(days, commit_count_day, W7)
    commits_30d = rolling_sum(days, commit_count_day, W30)
    files_added_1d = rolling_sum(days, files_added_day, W1)
    files_added_7d = rolling_sum(days, files_added_day, W7)
    files_added_30d = rolling_sum(days, files_added_day, W30)
    files_deleted_1d = rolling_sum(days, files_deleted_day, W1)
    files_deleted_7d = rolling_sum(days, files_deleted_day, W7)
    files_deleted_30d = rolling_sum(days, files_deleted_day, W30)

    # Rolling unique counts for authors and files_changed
    authors_1d = rolling_unique_count(days, authors_day, W1)
    authors_7d = rolling_unique_count(days, authors_day, W7)
    authors_30d = rolling_unique_count(days, authors_day, W30)
    files_changed_1d = rolling_unique_count(days, files_changed_day, W1)
    files_changed_7d = rolling_unique_count(days, files_changed_day, W7)
    files_changed_30d = rolling_unique_count(days, files_changed_day, W30)

    # Running maxima for loc_total at each window
    loc_total_1d = rolling_sum(days, loc_total_day, W1)
    loc_total_7d = rolling_sum(days, loc_total_day, W7)
    loc_total_30d = rolling_sum(days, loc_total_day, W30)
    max_loc_total_1d = running_maxima(days, loc_total_1d)
    max_loc_total_7d = running_maxima(days, loc_total_7d)
    max_loc_total_30d = running_maxima(days, loc_total_30d)

    # Cumulative series
    cum_loc_delta = cumulative_series(days, loc_delta_day)
    cum_files_delta = cumulative_series(days, files_delta_day)

    # Language LOC per day: sum (adds+deletes) per file per lang_from_path
    lang_loc_day: dict[int, dict[str, int]] = {t: {} for t in days}
    for commit in commits:
        day = (commit.timestamp // DAY_SECONDS) * DAY_SECONDS
        for f in commit.files:
            lang = lang_from_path(f.path)
            total = f.adds + f.deletes
            if total > 0:
                lang_loc_day[day][lang] = lang_loc_day[day].get(lang, 0) + total
    lang_mix_7d = compute_language_mix_7d(days, lang_loc_day)

    # Change sizes: per-commit totals of (adds+deletes)
    sizes_on_day: dict[int, list[int]] = {t: [] for t in days}
    for commit in commits:
        day = (commit.timestamp // DAY_SECONDS) * DAY_SECONDS
        commit_total = sum(f.adds + f.deletes for f in commit.files)
        if commit_total > 0:
            sizes_on_day[day].append(commit_total)
    change_size_dist = compute_change_size_distribution_7d(days, sizes_on_day)

    # Build list of loc_added_7d values for WoW delta
    loc_added_7d_list = [loc_added_7d[t] for t in days]
    commits_7d_list = [commits_7d[t] for t in days]
    files_changed_7d_list = [files_changed_7d[t] for t in days]

    # Assemble DayMetrics
    result: list[DayMetrics] = []
    for i, t in enumerate(days):
        delta_loc = compute_wow_delta(loc_added_7d_list, i)
        delta_commits = compute_wow_delta(commits_7d_list, i)
        delta_files = compute_wow_delta(files_changed_7d_list, i)
        median, p90 = change_size_dist[t]

        m = DayMetrics(
            timestamp=t,
            loc_added_1d=loc_added_1d[t],
            loc_added_7d=loc_added_7d[t],
            loc_added_30d=loc_added_30d[t],
            loc_deleted_1d=loc_deleted_1d[t],
            loc_deleted_7d=loc_deleted_7d[t],
            loc_deleted_30d=loc_deleted_30d[t],
            commits_1d=commits_1d[t],
            commits_7d=commits_7d[t],
            commits_30d=commits_30d[t],
            authors_1d=authors_1d[t],
            authors_7d=authors_7d[t],
            authors_30d=authors_30d[t],
            files_changed_1d=files_changed_1d[t],
            files_changed_7d=files_changed_7d[t],
            files_changed_30d=files_changed_30d[t],
            files_added_1d=files_added_1d[t],
            files_added_7d=files_added_7d[t],
            files_added_30d=files_added_30d[t],
            files_deleted_1d=files_deleted_1d[t],
            files_deleted_7d=files_deleted_7d[t],
            files_deleted_30d=files_deleted_30d[t],
            max_loc_total_1d=max_loc_total_1d[t],
            max_loc_total_7d=max_loc_total_7d[t],
            max_loc_total_30d=max_loc_total_30d[t],
            cumulative_loc_delta=cum_loc_delta[t],
            cumulative_files_delta=cum_files_delta[t],
            churn_7d=compute_churn(loc_added_7d[t], loc_deleted_7d[t]),
            churn_30d=compute_churn(loc_added_30d[t], loc_deleted_30d[t]),
            efficiency_7d=compute_efficiency(loc_added_7d[t], loc_deleted_7d[t]),
            efficiency_30d=compute_efficiency(loc_added_30d[t], loc_deleted_30d[t]),
            delta_loc_7d=delta_loc,
            delta_commits_7d=delta_commits,
            delta_files_7d=delta_files,
            arrow_loc=format_trend_arrow(delta_loc),
            arrow_commits=format_trend_arrow(delta_commits),
            arrow_files=format_trend_arrow(delta_files),
            lang_mix_7d=lang_mix_7d[t],
            change_median_7d=median,
            change_p90_7d=p90,
        )
        result.append(m)

    return result
