#!/usr/bin/env python3
"""Stitch cleaned per-clip EDLs into chapter videos from config/chapters.json."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DEFAULT_EDIT_DIR, helpers_dir, load_config

ROOT = Path(__file__).resolve().parent.parent
BATCH_DIR = DEFAULT_EDIT_DIR
EDLS = BATCH_DIR / "edls"
OUTPUT = BATCH_DIR / "output" / "chapters"
CFG = load_config()


def load_chapters() -> list[dict]:
    decisions_path = BATCH_DIR / "director" / "decisions.json"
    if decisions_path.exists():
        data = json.loads(decisions_path.read_text())
        chapters = data.get("stitch", {}).get("chapters") or []
        if chapters:
            return chapters
    path = ROOT / "config" / "chapters.json"
    if not path.exists():
        path = ROOT / "config" / "chapters.example.json"
    data = json.loads(path.read_text())
    return data["chapters"]


def build_chapter_edl(stems: list[str]) -> dict:
    sources: dict[str, str] = {}
    ranges: list[dict] = []
    for stem in stems:
        clip_edl = json.loads((EDLS / f"{stem}.json").read_text())
        sources.update(clip_edl["sources"])
        ranges.extend(clip_edl["ranges"])
    total = round(sum(float(r["end"]) - float(r["start"]) for r in ranges), 2)
    return {
        "version": 1,
        "mode": "pacing-cleanup",
        "chapter_stems": stems,
        "sources": sources,
        "ranges": ranges,
        "grade": CFG.get("grade", "none"),
        "subtitle_style": CFG.get("subtitle_style", "manrope-speech"),
        "fontsdir": "fonts",
        "subtitles": "master.srt",
        "total_duration_s": total,
    }


def render_chapter(slug: str, edl: dict) -> Path:
    helpers = helpers_dir()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    edl_path = BATCH_DIR / f"_chapter_{slug}.json"
    edl_path.write_text(json.dumps(edl, indent=2))
    out = OUTPUT / f"{slug}.mp4"
    preview = ["--preview"] if CFG.get("render_preview", True) else []
    cmd = [
        sys.executable,
        str(helpers / "render.py"),
        str(edl_path),
        "-o", str(out),
        *preview,
        "--build-subtitles",
    ]
    print(f"\n=== {slug} ({edl['total_duration_s']}s) ===", flush=True)
    subprocess.run(cmd, check=True, cwd=str(BATCH_DIR))
    return out


def main() -> None:
    force = "--force" in sys.argv
    if not force:
        script = Path(__file__).resolve().parent / "director.py"
        proc = subprocess.run(
            [sys.executable, str(script), "gate", "stitch"], cwd=str(BATCH_DIR)
        )
        if proc.returncode != 0:
            sys.exit(
                "Director gate blocked stitch. Update edit/director/decisions.json or pass --force"
            )
    manifest = []
    for ch in load_chapters():
        slug = ch["slug"]
        stems = ch["clips"]
        edl = build_chapter_edl(stems)
        out = render_chapter(slug, edl)
        manifest.append({
            "file": out.name,
            "title": ch.get("title", slug),
            "description": ch.get("description", ""),
            "clips": stems,
            "duration_s": edl["total_duration_s"],
        })
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nDone — {len(manifest)} chapters → {OUTPUT}/")


if __name__ == "__main__":
    main()
