import datetime
import pathlib
import subprocess

from typing import Any, Dict, Iterator, Optional


Commit = Dict[str, Any]
Blame = Dict[int, Commit]
CommitMap = Dict[str, Optional[Commit]]


class GitRepo:
    def __init__(
        self,
        repo_path: pathlib.Path,
        git_path: pathlib.Path = None,
        cmd_path: str = "git",
    ):
        self.repo_path = repo_path.resolve()
        self.git_path = git_path or self.repo_path.joinpath(".git")
        self.cmd_path = cmd_path

    def git(self, *args) -> subprocess.CompletedProcess:
        cmd_args = [
            self.cmd_path,
            "--work-tree",
            str(self.repo_path),
            "--git-dir",
            str(self.git_path),
        ] + list(args)
        return subprocess.run(cmd_args, capture_output=True, cwd=self.repo_path)

    def git_test(self, *args) -> bool:
        return self.git(*args).returncode == 0

    def git_output(self, *args) -> str:
        return self.git(*args).stdout.decode().strip()

    def fromtimestamp(self, timestamp):
        return datetime.datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d")

    def rev_parse(self, tag: str) -> str:
        return self.git_output("rev-parse", tag)

    def rev_list(self, tag: str) -> str:
        return self.git_output("rev-list", "-1", tag)

    def is_ancestor(self, parent, child) -> bool:
        return self.git_test("merge-base", "--is-ancestor", parent, child)

    def blame_file(self, file_path: pathlib.Path, changes_since: str = None) -> Blame:
        if changes_since:
            changes_since = self.rev_list(changes_since)
        if not file_path.is_absolute():
            file_path = self.repo_path.joinpath(file_path)
        blame = self.git_output("blame", "-p", "--incremental", file_path)
        lines = iter(blame.splitlines())
        commits: CommitMap = {}
        while True:
            try:
                self._parse_blame_line(lines, commits, changes_since=changes_since)
            except StopIteration:
                break
        if changes_since:
            commits.pop(changes_since, None)
        line_commits: Blame = {}
        for commit in commits.values():
            if commit is None:
                continue
            for line_num in commit["lines"]:
                line_commits[line_num] = commit
            del commit["lines"]
            commit["date"] = self.fromtimestamp(commit["author-time"])
        return line_commits

    def _parse_blame_line(
        self, lines: Iterator, commits: CommitMap, changes_since: str = None
    ):
        line = next(lines)
        if not line:
            raise StopIteration()
        commit_hash, _, line_num, line_count, *_ = line.split()
        line_num = int(line_num)
        line_count = int(line_count)
        if commit_hash in commits:
            commit = commits.get(commit_hash)
            if commit:
                commit["lines"].update(range(line_num, line_num + line_count))
            self._skip_blame_commit(lines)
        else:
            if changes_since and (
                changes_since == commit_hash
                or not self.is_ancestor(changes_since, commit_hash)
            ):
                commit = None
                self._skip_blame_commit(lines)
            else:
                commit = self._parse_blame_commit(lines)
                commit["hash"] = commit_hash
                commit["lines"] = set(range(line_num, line_num + line_count))
            commits[commit_hash] = commit

    @staticmethod
    def _skip_blame_commit(lines: Iterator):
        for line in lines:
            if line.startswith("filename "):
                break

    @staticmethod
    def _parse_blame_commit(lines: Iterator) -> Commit:
        commit = {}
        for line in lines:
            try:
                k, v = line.split(" ", 1)
            except ValueError:
                continue
            commit[k] = v.strip()
            if k == "filename":
                break
        return commit
