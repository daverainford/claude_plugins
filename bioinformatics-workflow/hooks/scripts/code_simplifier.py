#!/usr/bin/env python3
"""Remind the model to run code-simplifier after every code write. Fires unconditionally on match."""
import os

from _common import emit, file_path, read_event

CODE_EXTENSIONS = {".py", ".r", ".sh", ".ts", ".sql", ".js", ".mjs", ".tsx"}
CDK_FILES = {"cdk.json"}


def main():
    path = file_path(read_event())
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    if ext not in CODE_EXTENSIONS and name not in CDK_FILES:
        return
    emit(
        f"Code was just written or modified ({path}) — run the `code-simplifier` agent "
        "(or `/simplify`) on this file before considering the task complete."
    )


if __name__ == "__main__":
    main()
