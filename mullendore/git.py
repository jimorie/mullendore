import datetime
import pathlib
import subprocess

from typing import Union, Mapping, Iterator

Commit = Mapping[str, str]
Blame = Mapping[int, Commit]


class GitRepo:
    def __init__(self, repo_path: pathlib.Path, cmd_path: pathlib.Path = "git"):
        self.repo_path = repo_path.resolve()
        self.cmd_path = cmd_path

    def git(self, *args, return_code=False) -> Union[str, bool]:
        args = [self.cmd_path] + list(args)
        process = subprocess.run(args, capture_output=True, cwd=self.repo_path)
        if return_code:
            return process.returncode == 0
        process.check_returncode()
        return process.stdout.decode().strip()

    def fromtimestamp(self, timestamp):
        return datetime.datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d")

    def rev_parse(self, tag: str):
        return self.git("rev-parse", tag)

    def rev_list(self, tag: str):
        return self.git("rev-list", "-1", tag)

    def is_ancestor(self, parent, child):
        return self.git("merge-base", "--is-ancestor", parent, child, return_code=True)

    def blame_file(self, file_path: pathlib.Path, changes_since: str = None) -> Blame:
        if changes_since:
            changes_since = self.rev_list(changes_since)
        if not file_path.is_absolute():
            file_path = self.repo_path.joinpath(file_path)
        blame = self.git("blame", "-p", "--incremental", file_path)
        lines = iter(blame.splitlines())
        commits = {}
        while True:
            try:
                self._parse_blame_line(lines, commits, changes_since=changes_since)
            except StopIteration:
                break
        if changes_since:
            commits.pop(changes_since, None)
        line_commits = {}
        for commit in commits.values():
            if commit is False:
                continue
            for line_num in commit["lines"]:
                line_commits[line_num] = commit
            del commit["lines"]
            commit["date"] = self.fromtimestamp(commit["author-time"])
        return line_commits

    def _parse_blame_line(
        self, lines: Iterator, commits: Mapping, changes_since: str = None
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
                commit = False
                self._skip_blame_commit(lines)
            else:
                commit = self._parse_blame_commit(lines)
                commit["hash"] = commit_hash
                commit["lines"] = set(range(line_num, line_num + line_count))
            commits[commit_hash] = commit

    @staticmethod
    def _skip_blame_commit(lines):
        for line in lines:
            if line.startswith("filename "):
                break

    @staticmethod
    def _parse_blame_commit(lines):
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
