"""Build a pacing-cleanup EDL from a word-level transcript.

Speech-cleanup mode: keep chronological order, remove pauses and filler words,
do NOT reorganize into narrative beats. The speaker's message stays intact —
only dead air and verbal clutter are cut.

Usage:
    python helpers/build_pacing_edl.py <video> --edit-dir <edit_dir>
    python helpers/build_pacing_edl.py <video> --edit-dir <edit_dir> --min-pause 0.35
    python helpers/build_pacing_edl.py <video> --edit-dir <edit_dir> --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_FILLERS = frozenset({
    "um", "umm", "uh", "uhh", "er", "err", "ah", "hmm", "hm", "mhm", "eh",
})

PAD_BEFORE_S = 0.05
PAD_AFTER_S = 0.08


def load_words(transcript_path: Path) -> list[dict]:
    data = json.loads(transcript_path.read_text())
    words: list[dict] = []
    for w in data.get("words", []):
        if w.get("type") not in (None, "word"):
            continue
        text = (w.get("text") or "").strip()
        start = w.get("start")
        end = w.get("end")
        if not text or start is None or end is None:
            continue
        words.append({"text": text, "start": float(start), "end": float(end)})
    words.sort(key=lambda x: x["start"])
    return words


def is_filler(text: str, fillers: frozenset[str]) -> bool:
    normalized = re.sub(r"[^\w']", "", text.lower())
    return normalized in fillers


def build_kept_ranges(
    words: list[dict],
    *,
    min_pause: float,
    fillers: frozenset[str],
    pad_before: float,
    pad_after: float,
    video_duration: float | None = None,
) -> list[tuple[float, float]]:
    """Return (start, end) source-time ranges to KEEP, in order."""
    kept: list[tuple[float, float]] = []
    seg_start: float | None = None
    seg_end: float | None = None
    prev_end: float | None = None

    def flush() -> None:
        nonlocal seg_start, seg_end
        if seg_start is None or seg_end is None:
            return
        start = max(0.0, seg_start - pad_before)
        end = seg_end + pad_after
        if video_duration is not None:
            end = min(end, video_duration)
        if end > start:
            kept.append((start, end))
        seg_start = None
        seg_end = None

    for w in words:
        if is_filler(w["text"], fillers):
            continue

        gap = (w["start"] - prev_end) if prev_end is not None else 0.0
        if seg_start is None:
            seg_start = w["start"]
            seg_end = w["end"]
        elif gap >= min_pause:
            flush()
            seg_start = w["start"]
            seg_end = w["end"]
        else:
            seg_end = w["end"]

        prev_end = w["end"]

    flush()
    return kept


def probe_duration(video: Path) -> float | None:
    import subprocess

    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(video),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def summarize(words: list[dict], ranges: list[tuple[float, float]], source_duration: float | None) -> str:
    kept_s = sum(b - a for a, b in ranges)
    src_s = source_duration or (words[-1]["end"] if words else 0.0)
    removed_s = max(0.0, src_s - kept_s)
    pct = (removed_s / src_s * 100) if src_s > 0 else 0.0
    return (
        f"{len(ranges)} kept segment(s), "
        f"{kept_s:.1f}s output from {src_s:.1f}s source "
        f"({removed_s:.1f}s removed, {pct:.0f}%)"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a pacing-cleanup EDL from transcript")
    ap.add_argument("video", type=Path, help="Source video path")
    ap.add_argument("--edit-dir", type=Path, required=True, help="Edit directory (transcripts/ lives here)")
    ap.add_argument("--min-pause", type=float, default=0.25, help="Cut pauses >= this many seconds (default 0.25)")
    ap.add_argument("--pad-before", type=float, default=PAD_BEFORE_S)
    ap.add_argument("--pad-after", type=float, default=PAD_AFTER_S)
    ap.add_argument("--filler", action="append", default=[], help="Extra filler word (repeatable)")
    ap.add_argument("--no-fillers", action="store_true", help="Only cut pauses, keep filler words")
    ap.add_argument("--grade", default="none", help="Grade preset for render.py (default: none)")
    ap.add_argument(
        "--subtitle-style",
        default="manrope-speech",
        help="Subtitle preset for render.py (default: manrope-speech)",
    )
    ap.add_argument("-o", "--output", type=Path, help="EDL output path (default: <edit-dir>/edl.json)")
    ap.add_argument("--dry-run", action="store_true", help="Print summary only, do not write EDL")
    args = ap.parse_args()

    video = args.video.resolve()
    edit_dir = args.edit_dir.resolve()
    stem = video.stem
    transcript_path = edit_dir / "transcripts" / f"{stem}.json"

    if not transcript_path.exists():
        sys.exit(f"transcript not found: {transcript_path}\nRun transcribe.py first.")

    words = load_words(transcript_path)
    if not words:
        sys.exit(f"no words in transcript: {transcript_path}")

    fillers = frozenset() if args.no_fillers else DEFAULT_FILLERS | frozenset(w.lower() for w in args.filler)
    duration = probe_duration(video)
    ranges = build_kept_ranges(
        words,
        min_pause=args.min_pause,
        fillers=fillers,
        pad_before=args.pad_before,
        pad_after=args.pad_after,
        video_duration=duration,
    )

    summary = summarize(words, ranges, duration)
    print(summary)

    if args.dry_run:
        for i, (a, b) in enumerate(ranges):
            print(f"  [{i:02d}] {a:7.2f}-{b:7.2f}  ({b - a:5.2f}s)")
        return

    edl = {
        "version": 1,
        "mode": "pacing-cleanup",
        "sources": {stem: str(video)},
        "ranges": [
            {
                "source": stem,
                "start": round(a, 3),
                "end": round(b, 3),
                "note": "speech",
                "reason": f"pacing cleanup (pause >= {args.min_pause:.2f}s)",
            }
            for a, b in ranges
        ],
        "grade": args.grade,
        "subtitle_style": args.subtitle_style,
        "subtitles": "master.srt",
        "pacing": {
            "min_pause_s": args.min_pause,
            "pad_before_s": args.pad_before,
            "pad_after_s": args.pad_after,
            "fillers_removed": sorted(fillers),
        },
        "total_duration_s": round(sum(b - a for a, b in ranges), 2),
    }

    out_path = (args.output or edit_dir / "edl.json").resolve()
    out_path.write_text(json.dumps(edl, indent=2))
    print(f"EDL → {out_path}")


if __name__ == "__main__":
    main()
