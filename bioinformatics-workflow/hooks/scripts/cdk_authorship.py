#!/usr/bin/env python3
"""Flag CDK infrastructure files as a checkpoint for the aws-dev-toolkit authorship rule.

Does not verify which skill authored the file; it only marks the file type.
"""
import os
import re

from _common import emit, file_path, read_event

CDK_PATH = re.compile(r"(^|/)cdk/|(^|/)cdk\.json$|[-_]stack\.(ts|js|py)$", re.IGNORECASE)
SOURCE_EXTENSIONS = {".ts", ".js", ".py"}


def inside_cdk_app(path):
    """True if a parent directory holds cdk.json, i.e. the project's own CDK layout."""
    if os.path.splitext(path)[1].lower() not in SOURCE_EXTENSIONS:
        return False
    directory = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isfile(os.path.join(directory, "cdk.json")):
            return True
        parent = os.path.dirname(directory)
        if parent == directory:
            return False
        directory = parent


def main():
    path = file_path(read_event())
    if not path or not (CDK_PATH.search(path.replace(os.sep, "/")) or inside_cdk_app(path)):
        return
    emit(
        f"This looks like CDK infrastructure code ({path}) — confirm this was authored via the "
        "`aws-dev-toolkit` plugin's skills (analysis-workflow section 7.1), not hand-written. "
        "If aws-dev-toolkit is not enabled, stop and ask the user to run "
        "`/plugin install aws-dev-toolkit@david-plugins`."
    )


if __name__ == "__main__":
    main()
