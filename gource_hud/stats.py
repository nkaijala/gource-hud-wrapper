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
