#!/usr/bin/env python3
"""Extract the exact executable paths observed by the CI runtime trace."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


EXEC_RE = re.compile(r"^(?:execve|execveat)\((.*)$")
QUOTED_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def executable_from_line(line: str) -> str | None:
    match = EXEC_RE.match(line.strip())
    if not match or not line.rstrip().endswith("= 0"):
        return None
    quoted = QUOTED_RE.findall(match.group(1))
    if not quoted:
        return None
    # execve(path, ...); execveat(fd, path, ...). The first absolute path is
    # the executable in both forms and avoids depending on strace formatting.
    for value in quoted:
        decoded = ast.literal_eval(value)
        if decoded.startswith("/"):
            return decoded
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    paths: set[str] = set()
    for trace in sorted(args.trace_directory.glob("exec*")):
        for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
            executable = executable_from_line(line)
            if executable:
                paths.add(executable)

    rendered = "\n".join(sorted(paths)) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
