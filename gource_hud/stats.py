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
