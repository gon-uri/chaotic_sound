#!/usr/bin/env python3
"""PostToolUse hook: format a Python file under ``lab/`` with ruff after Claude edits it.

Claude Code passes the tool call as JSON on stdin; we only need ``tool_input.file_path``.
The hook never blocks: any failure exits 0 so an edit is never reported as an error.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    file_path = (data.get("tool_input") or {}).get("file_path") or ""
    if not file_path.endswith(".py"):
        return
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
    lab = root / "lab"
    path = Path(file_path).resolve()
    if lab not in path.parents:
        return
    base = ["uv", "run", "--project", str(lab), "ruff"]
    subprocess.run([*base, "check", "--select", "I", "--fix", "--quiet", str(path)], cwd=lab)
    subprocess.run([*base, "format", "--quiet", str(path)], cwd=lab)


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
