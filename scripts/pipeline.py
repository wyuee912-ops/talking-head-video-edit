#!/usr/bin/env python3
"""End-to-end pipeline with director gates.

Usage:
    python scripts/pipeline.py status
    python scripts/pipeline.py plan          # transcribe + edl + director brief
    python scripts/pipeline.py sample STEM
    python scripts/pipeline.py batch [--force]
    python scripts/pipeline.py stitch [--force]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent


def run(script: str, *args: str) -> None:
    cmd = [sys.executable, str(SCRIPTS / script), *args]
    print(f"\n>>> {' '.join(cmd)}\n", flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> None:
    step = sys.argv[1] if len(sys.argv) > 1 else "status"
    force = "--force" in sys.argv

    if step == "status":
        run("director.py", "validate")
        return

    if step == "plan":
        run("director.py", "init")
        run("batch.py", "transcribe")
        run("batch.py", "edl")
        run("director.py", "inventory")
        run("director.py", "brief")
        print("\nNext: read edit/director/brief.md, discuss with user, update edit/director/decisions.json")
        return

    if step == "sample":
        stem = sys.argv[2] if len(sys.argv) > 2 else ""
        args = ["sample", stem] if stem else ["sample"]
        run("batch.py", *args)
        return

    if step == "batch":
        if not force:
            run("director.py", "gate", "batch")
        extra = ["--force"] if force else []
        run("batch.py", "render", *extra)
        return

    if step == "stitch":
        if not force:
            run("director.py", "gate", "stitch")
        run("director.py", "apply")
        run("stitch_chapters.py")
        return

    print(__doc__)


if __name__ == "__main__":
    main()
