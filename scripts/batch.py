#!/usr/bin/env python3
"""Batch speech-cleanup pipeline for talking-head footage.

Always render ONE sample clip first and wait for user approval before batch render.

Usage:
    python scripts/batch.py transcribe
    python scripts/batch.py edl
    python scripts/batch.py sample [STEM]
    python scripts/batch.py snapshot [STEM] [SECONDS]
    python scripts/batch.py render [--force]
    python scripts/batch.py help
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DEFAULT_EDIT_DIR, helpers_dir, load_config

BATCH_DIR = DEFAULT_EDIT_DIR
SOURCES = BATCH_DIR / "sources"
EDLS = BATCH_DIR / "edls"
OUTPUT = BATCH_DIR / "output"
VERIFY = BATCH_DIR / "verify"
DECISIONS_PATH = BATCH_DIR / "director" / "decisions.json"
CFG = load_config()
MIN_PAUSE = CFG.get("min_pause_s", 0.25)
SUBTITLE_STYLE = CFG.get("subtitle_style", "manrope-speech")
LANGUAGE = CFG.get("language", "en")
WORKERS = CFG.get("transcribe_workers", 4)


def check_gate(step: str, force: bool) -> None:
    if force:
        return
    script = Path(__file__).resolve().parent / "director.py"
    proc = subprocess.run([sys.executable, str(script), "gate", step], cwd=BATCH_DIR)
    if proc.returncode != 0:
        sys.exit(
            f"Director gate blocked '{step}'. Update edit/director/decisions.json or pass --force"
        )


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print(f"$ {' '.join(cmd[:8])}{' …' if len(cmd) > 8 else ''}", flush=True)
    subprocess.run(cmd, check=True, cwd=cwd or BATCH_DIR)


def render_one(stem: str, *, suffix: str = "_clean") -> Path:
    helpers = helpers_dir()
    edl_path = EDLS / f"{stem}.json"
    if not edl_path.exists():
        sys.exit(f"EDL not found: {edl_path}. Run: python scripts/batch.py edl")

    out = OUTPUT / f"{stem}{suffix}.mp4"
    OUTPUT.mkdir(parents=True, exist_ok=True)

    edl = json.loads(edl_path.read_text())
    edl["subtitle_style"] = SUBTITLE_STYLE
    edl["fontsdir"] = "fonts"
    render_edl = BATCH_DIR / "_render_edl.json"
    render_edl.write_text(json.dumps(edl, indent=2))

    for tmp_dir in (BATCH_DIR / "clips_preview",):
        if tmp_dir.exists():
            for p in tmp_dir.glob("*.mp4"):
                p.unlink()
    for tmp in (BATCH_DIR / "base_preview.mp4", BATCH_DIR / "master.srt"):
        if tmp.exists():
            tmp.unlink()

    preview_flag = ["--preview"] if CFG.get("render_preview", True) else []
    run([
        sys.executable,
        str(helpers / "render.py"),
        str(render_edl),
        "-o", str(out),
        *preview_flag,
        "--build-subtitles",
    ])
    return out


def snapshot(stem: str, at_s: float = 3.5) -> Path:
    video = OUTPUT / f"{stem}_sample.mp4"
    if not video.exists():
        video = OUTPUT / f"{stem}_clean.mp4"
    if not video.exists():
        sys.exit(f"No rendered video for {stem}. Run sample or render first.")

    VERIFY.mkdir(parents=True, exist_ok=True)
    out = VERIFY / f"{stem}_caption_preview.jpg"
    run([
        "ffmpeg", "-y", "-ss", str(at_s), "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(out),
    ])
    print(f"snapshot → {out}")
    return out


def main() -> None:
    step = sys.argv[1] if len(sys.argv) > 1 else "help"
    helpers = helpers_dir()
    videos = sorted(SOURCES.glob("*"))
    videos = [v for v in videos if v.suffix.lower() in {".mov", ".mp4", ".mkv"}]

    if step == "sample":
        stem = sys.argv[2] if len(sys.argv) > 2 else None
        if not stem:
            stems = [v.stem for v in videos]
            stem = CFG.get("default_sample_stem") or (stems[len(stems) // 2] if stems else None)
        if not stem:
            sys.exit("No sources in edit/sources/. Add .mov/.mp4 files first.")
        out = render_one(stem, suffix="_sample")
        snap = snapshot(stem)
        print(f"\nApproval sample → {out}")
        print(f"Caption snapshot → {snap}")
        print("Review pacing + captions. Approve before: python scripts/batch.py render --force")
        return

    if step == "snapshot":
        stem = sys.argv[2] if len(sys.argv) > 2 else sys.exit("usage: batch.py snapshot STEM [SECONDS]")
        at_s = float(sys.argv[3]) if len(sys.argv) > 3 else 3.5
        snapshot(stem, at_s)
        return

    if step in ("transcribe", "all"):
        run([
            sys.executable,
            str(helpers / "transcribe_batch.py"),
            str(SOURCES.resolve()),
            "--edit-dir", str(BATCH_DIR.resolve()),
            "--workers", str(WORKERS),
            "--language", LANGUAGE,
        ])

    if step in ("edl", "all"):
        EDLS.mkdir(parents=True, exist_ok=True)
        manifest: list[dict] = []
        for video in videos:
            edl_path = EDLS / f"{video.stem}.json"
            run([
                sys.executable,
                str(helpers / "build_pacing_edl.py"),
                str(video.resolve()),
                "--edit-dir", str(BATCH_DIR.resolve()),
                "--min-pause", str(MIN_PAUSE),
                "--subtitle-style", SUBTITLE_STYLE,
                "--grade", CFG.get("grade", "none"),
                "-o", str(edl_path.resolve()),
            ])
            edl = json.loads(edl_path.read_text())
            manifest.append({
                "source": video.name,
                "edl": edl_path.name,
                "output_s": edl.get("total_duration_s"),
                "segments": len(edl.get("ranges", [])),
            })
        (BATCH_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"\nmanifest: {len(manifest)} clips")

    if step == "render":
        check_gate("batch", "--force" in sys.argv)
        force = "--force" in sys.argv
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for edl_path in sorted(EDLS.glob("*.json")):
            out = OUTPUT / f"{edl_path.stem}_clean.mp4"
            if not force and out.exists() and out.stat().st_size > 0:
                print(f"skip (exists): {out.name}")
                continue
            render_one(edl_path.stem)

    if step == "help":
        print(__doc__)
        return

    print("done.")


if __name__ == "__main__":
    main()
