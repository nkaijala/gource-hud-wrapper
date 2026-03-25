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
