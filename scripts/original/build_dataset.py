#!/usr/bin/env python3
"""
Build the analysis-ready CSV from study.sqlite3.

Outputs:
  data/analysis_prs.csv

Key derived variables:
- pr_size = additions + deletions
- first_external_human_review_at
- first_review_latency_hours
- merge_latency_hours
- contributor_experience = count of the author's PRs in the SAME repository
  that had already been merged before this PR was created
"""

import bisect
import csv
import os
import sqlite3
import numpy as np
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = os.getenv("STUDY_DB", "study.sqlite3")
OUTPUT = Path("data/analysis_prs.csv")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def hours_between(a: Optional[str], b: Optional[str]) -> Optional[float]:
    """Return b-a in hours."""
    da, db = parse_dt(a), parse_dt(b)
    if not da or not db:
        return None
    return (db - da).total_seconds() / 3600.0


BOT_LOGINS = {
    "renovate",
    "dependabot",
    "greenkeeper",
    "snyk-bot",
    "mergify",
    "semantic-release-bot",
    "github-actions",
}

def is_bot(login: Optional[str], actor_type: Optional[str]) -> bool:
    if actor_type == "Bot":
        return True

    if not login:
        return False

    login = login.lower()

    if login.endswith("[bot]"):
        return True

    if login in BOT_LOGINS:
        return True

    if "dependabot" in login:
        return True

    if "renovate" in login:
        return True

    return False

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1) Build exact historical contributor experience.
    # A previous PR counts only if it was ALREADY MERGED before the studied PR
    # was created. This avoids look-ahead bias.
    merged_times = defaultdict(list)

    for row in conn.execute(
        """
        SELECT p.repo, p.author_login, p.merged_at
        FROM pull_requests p
        JOIN repositories r ON r.name = p.repo
        WHERE p.merged = 1
        AND p.merged_at IS NOT NULL
        AND p.author_login IS NOT NULL
        AND r.status = 'done'
        ORDER BY p.repo, p.author_login, p.merged_at
        """
    ):
        merged_times[(row["repo"], row["author_login"])].append(
            parse_dt(row["merged_at"])
        )

    # 2) Load analysis PRs.
    prs = list(
        conn.execute(
            """
            SELECT
              p.*,
              r.stars AS repo_stars,
              r.language AS repo_language,
              r.license_spdx AS repo_license
            FROM pull_requests p
            JOIN repositories r ON r.name=p.repo
            WHERE p.is_analysis_period=1
            AND r.status = 'done'
            ORDER BY p.repo, p.created_at, p.number
            """
        )
    )

    author_by_pr = {
        (row["repo"], row["number"]): (row["author_login"], row["author_type"])
        for row in prs
    }

    # 3) Find first submitted formal review and first external HUMAN formal review.
    first_any = {}
    first_external_human = {}
    first_external_human_reviewer = {}

    for rv in conn.execute(
        """
        SELECT
            rv.repo,
            rv.pr_number,
            rv.submitted_at,
            rv.state,
            rv.reviewer_login,
            rv.reviewer_type
        FROM reviews rv
        JOIN repositories r ON r.name = rv.repo
        WHERE rv.submitted_at IS NOT NULL
        AND r.status = 'done'
        ORDER BY rv.repo, rv.pr_number, rv.submitted_at
        """
    ):
        key = (rv["repo"], rv["pr_number"])

        if key not in first_any:
            first_any[key] = rv["submitted_at"]

        pr_author, _ = author_by_pr.get(key, (None, None))
        reviewer = rv["reviewer_login"]

        if key in first_external_human:
            continue
        if is_bot(reviewer, rv["reviewer_type"]):
            continue
        if reviewer and pr_author and reviewer.lower() == pr_author.lower():
            continue

        first_external_human[key] = rv["submitted_at"]
        first_external_human_reviewer[key] = reviewer

    columns = [
        "repo",
        "repo_language",
        "repo_stars",
        "repo_license",
        "pr_number",
        "url",
        "author_login",
        "author_type",
        "author_association",
        "created_at",
        "year",
        "merged",
        "merged_at",
        "state",
        "is_draft_now",
        "had_ready_for_review_event",
        "ready_for_review_at",
        "additions",
        "deletions",
        "pr_size",
        "log_pr_size",
        "changed_files",
        "commit_count",
        "contributor_experience",
        "experience_log1p",
        "review_total_count",
        "first_any_formal_review_at",
        "first_external_human_review_at",
        "first_external_human_reviewer",
        "first_review_latency_hours",
        "log_first_review_latency",
        "merge_latency_hours",
        "log_merge_latency",
        "author_is_bot",
        "eligible_rq1_basic",
        "eligible_rq1_strict_no_draft_history",
        "eligible_merge_latency",
    ]

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()

        for row in prs:
            key = (row["repo"], row["number"])
            created_dt = parse_dt(row["created_at"])
            author = row["author_login"]

            history = merged_times.get((row["repo"], author), [])
            # Count only merges strictly BEFORE the current PR creation.
            experience = bisect.bisect_left(history, created_dt) if author else None

            first_review = first_external_human.get(key)
            review_latency = hours_between(row["created_at"], first_review)
            merge_latency = hours_between(row["created_at"], row["merged_at"])

            additions = row["additions"]
            deletions = row["deletions"]
            pr_size = (
                additions + deletions
                if additions is not None and deletions is not None
                else None
            )

            author_bot = is_bot(author, row["author_type"])
            had_ready = bool(row["had_ready_for_review_event"])

            eligible_rq1_basic = (
                first_review is not None
                and not author_bot
                and pr_size is not None
                and review_latency is not None
                and review_latency >= 0
            )

            # Strict sensitivity dataset: removes any PR that has a
            # ready_for_review event because time-from-creation may include
            # intentional draft time.
            eligible_rq1_strict = eligible_rq1_basic and not had_ready

            eligible_merge = (
                bool(row["merged"])
                and row["merged_at"] is not None
                and not author_bot
                and pr_size is not None
                and merge_latency is not None
                and merge_latency >= 0
            )

            log_pr_size = (
                np.log1p(pr_size)
                if pr_size is not None
                else None
            )

            experience_log1p = (
                np.log1p(experience)
                if experience is not None
                else None
            )

            log_first_review_latency = (
                np.log1p(review_latency)
                if review_latency is not None and review_latency >= 0
                else None
            )

            log_merge_latency = (
                np.log1p(merge_latency)
                if merge_latency is not None and merge_latency >= 0
                else None
            )

            writer.writerow(
                {
                    "repo": row["repo"],
                    "repo_language": row["repo_language"],
                    "repo_stars": row["repo_stars"],
                    "repo_license": row["repo_license"],
                    "pr_number": row["number"],
                    "url": row["url"],
                    "author_login": author,
                    "author_type": row["author_type"],
                    "author_association": row["author_association"],
                    "created_at": row["created_at"],
                    "year": created_dt.year if created_dt else None,
                    "merged": row["merged"],
                    "merged_at": row["merged_at"],
                    "state": row["state"],
                    "is_draft_now": row["is_draft"],
                    "had_ready_for_review_event": row["had_ready_for_review_event"],
                    "ready_for_review_at": row["ready_for_review_at"],
                    "additions": additions,
                    "deletions": deletions,
                    "pr_size": pr_size,
                    "changed_files": row["changed_files"],
                    "commit_count": row["commit_count"],
                    "contributor_experience": experience,
                    "review_total_count": row["review_total_count"],
                    "first_any_formal_review_at": first_any.get(key),
                    "first_external_human_review_at": first_review,
                    "first_external_human_reviewer": first_external_human_reviewer.get(key),
                    "first_review_latency_hours": review_latency,
                    "merge_latency_hours": merge_latency,
                    "author_is_bot": int(author_bot),
                    "eligible_rq1_basic": int(eligible_rq1_basic),
                    "eligible_rq1_strict_no_draft_history": int(eligible_rq1_strict),
                    "eligible_merge_latency": int(eligible_merge),
                    "log_pr_size": log_pr_size,
                    "experience_log1p": experience_log1p,
                    "log_first_review_latency": log_first_review_latency,
                    "log_merge_latency": log_merge_latency,
                }
            )

    print(f"Wrote {len(prs):,} analysis PRs to {OUTPUT}")


if __name__ == "__main__":
    main()
