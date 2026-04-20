#!/usr/bin/env python3
"""
Analyze Apache Camel issue-related commits using PyDriller.

Example:
python camel_issue_analysis.py \
  --issues CAMEL-180,CAMEL-321,CAMEL-1818,CAMEL-3214,CAMEL-18065 \
  --repo-url https://github.com/apache/camel
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydriller import Repository


TRACKED_CHANGE_TYPES = {"ADD", "MODIFY", "DELETE"}


def clone_repo(repo_url: str) -> tuple[str, str]:
    """
    Clone the target repository into a temporary directory.

    Returns:
        Tuple of (repo_path, temp_directory_path)
    """
    temp_dir = tempfile.mkdtemp(prefix="issue-commit-analysis-")
    repo_path = Path(temp_dir) / "repo"

    subprocess.run(
        ["git", "clone", repo_url, str(repo_path)],
        check=True,
    )

    return str(repo_path), temp_dir


def normalize_issues(raw_issues: str) -> list[str]:
    return [issue.strip().upper() for issue in raw_issues.split(",") if issue.strip()]


def find_matching_commits(repo_path: str, issues: list[str]) -> list[str]:
    """
    Find unique commit hashes with issue IDs in commit messages.
    """
    hashes: set[str] = set()
    for issue in issues:
        result = subprocess.run(
            [
                "git",
                "-C",
                repo_path,
                "log",
                "--all",
                "--format=%H",
                "--regexp-ignore-case",
                "--grep",
                issue,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            value = line.strip()
            if value:
                hashes.add(value)

    return sorted(hashes)


def file_path_for_change(modified_file) -> str | None:
    """
    Prefer new_path, fall back to old_path for deleted files.
    """
    return modified_file.new_path or modified_file.old_path


def calculate_metrics(repo_path: str, commit_hashes: list[str]) -> tuple[int, float, float]:
    total_files_changed = 0
    total_dmm_score = 0.0

    commit_count = len(commit_hashes)
    if commit_count == 0:
        return 0, 0.0, 0.0

    for commit_hash in commit_hashes:
        commits = list(Repository(repo_path, single=commit_hash).traverse_commits())
        if not commits:
            continue
        commit = commits[0]
        unique_files: set[str] = set()
        for modified_file in commit.modified_files:
            if modified_file.change_type.name not in TRACKED_CHANGE_TYPES:
                continue
            path = file_path_for_change(modified_file)
            if path:
                unique_files.add(path)

        total_files_changed += len(unique_files)

        dmm_unit_size = commit.dmm_unit_size if commit.dmm_unit_size is not None else 0.0
        dmm_complexity = (
            commit.dmm_unit_complexity if commit.dmm_unit_complexity is not None else 0.0
        )
        dmm_interfacing = (
            commit.dmm_unit_interfacing if commit.dmm_unit_interfacing is not None else 0.0
        )
        total_dmm_score += (dmm_unit_size + dmm_complexity + dmm_interfacing) / 3.0

    average_files_changed = total_files_changed / commit_count
    average_dmm = total_dmm_score / commit_count
    return commit_count, average_files_changed, average_dmm


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute average file changes and DMM metrics for issue-related commits."
    )
    parser.add_argument(
        "--issues",
        required=True,
        help="Comma-separated issue IDs (e.g. CAMEL-180,CAMEL-321)",
    )
    parser.add_argument(
        "--repo-url",
        required=False,
        help="Git repository URL (e.g. https://github.com/apache/camel)",
    )
    parser.add_argument(
        "--repo-path",
        required=False,
        help="Use an existing local repository path instead of cloning.",
    )
    args = parser.parse_args()

    if not args.repo_url and not args.repo_path:
        parser.error("Provide either --repo-url or --repo-path")

    issues = normalize_issues(args.issues)
    repo_path = ""
    temp_dir = ""
    try:
        if args.repo_path:
            repo_path = args.repo_path
        else:
            repo_path, temp_dir = clone_repo(args.repo_url)

        commit_hashes = find_matching_commits(repo_path, issues)
        commit_count, avg_files_changed, avg_dmm = calculate_metrics(repo_path, commit_hashes)
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"Total commits analyzed: {commit_count}")
    print(f"Average number of files changed: {avg_files_changed:.4f}")
    print(f"Average DMM metrics: {avg_dmm:.4f}")


if __name__ == "__main__":
    main()
