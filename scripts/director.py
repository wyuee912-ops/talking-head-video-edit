#!/usr/bin/env python3
"""Director agent — plan delivery format, chapters, and exclusions before rendering.

The director does NOT cut footage. It inventories transcripts, flags issues,
proposes delivery options, and records user-approved decisions in decisions.json.

Usage:
    python scripts/director.py inventory     # scan clips → inventory.json
    python scripts/director.py brief         # human/agent-readable plan → brief.md
    python scripts/director.py init          # create decisions.json (unapproved)
    python scripts/director.py validate      # print gate status
    python scripts/director.py gate sample   # exit 0 if sample step allowed
    python scripts/director.py gate batch    # exit 0 if batch approved
    python scripts/director.py gate stitch   # exit 0 if stitch approved
    python scripts/director.py apply         # write config/chapters.json from decisions
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DEFAULT_EDIT_DIR, ROOT, load_config

DIRECTOR_DIR = DEFAULT_EDIT_DIR / "director"
INVENTORY_PATH = DIRECTOR_DIR / "inventory.json"
BRIEF_PATH = DIRECTOR_DIR / "brief.md"
DECISIONS_PATH = DIRECTOR_DIR / "decisions.json"
CHAPTERS_PATH = ROOT / "config" / "chapters.json"

FRAGMENT_MAX_S = 1.5
THANK_YOU_RE = re.compile(r"^\s*thank you\.?\s*$", re.I)
QA_KEYWORDS = re.compile(
    r"\b(question|audience|Q&A|from the back|good morning)\b", re.I
)


def probe_duration(video: Path) -> float:
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
        return 0.0


def load_transcript(stem: str) -> dict | None:
    path = DEFAULT_EDIT_DIR / "transcripts" / f"{stem}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def transcript_text(tr: dict | None) -> str:
    if not tr:
        return ""
    return " ".join((tr.get("text") or "").split())


def classify_clip(stem: str, duration: float, text: str) -> list[str]:
    flags: list[str] = []
    if duration <= FRAGMENT_MAX_S:
        flags.append("fragment")
    if THANK_YOU_RE.match(text):
        flags.append("false_end")
    if QA_KEYWORDS.search(text):
        flags.append("qa")
    if len(text.split()) < 4:
        flags.append("very_short")
    return flags


def edl_stats(stem: str) -> dict:
    path = DEFAULT_EDIT_DIR / "edls" / f"{stem}.json"
    if not path.exists():
        return {"output_s": None, "segments": None, "trim_pct": None}
    edl = json.loads(path.read_text())
    src = probe_duration(Path(list(edl["sources"].values())[0]))
    out = float(edl.get("total_duration_s", 0))
    trim = round((1 - out / src) * 100, 1) if src > 0 else 0
    return {"output_s": out, "segments": len(edl.get("ranges", [])), "trim_pct": trim}


def build_inventory() -> list[dict]:
    sources = sorted(
        p for p in (DEFAULT_EDIT_DIR / "sources").glob("*")
        if p.suffix.lower() in {".mov", ".mp4", ".mkv"}
    )
    items: list[dict] = []
    for i, video in enumerate(sources, 1):
        stem = video.stem
        tr = load_transcript(stem)
        text = transcript_text(tr)
        duration = tr.get("duration") if tr else probe_duration(video)
        flags = classify_clip(stem, float(duration or 0), text)
        stats = edl_stats(stem)
        items.append({
            "order": i,
            "stem": stem,
            "file": video.name,
            "source_s": round(float(duration or 0), 2),
            "output_s": stats["output_s"],
            "segments": stats["segments"],
            "trim_pct": stats["trim_pct"],
            "flags": flags,
            "preview": text[:140] + ("…" if len(text) > 140 else ""),
        })
    return items


def total_output_s(items: list[dict]) -> float:
    return sum(float(i["output_s"] or i["source_s"]) for i in items)


def default_decisions() -> dict:
    return {
        "version": 1,
        "delivery": None,
        "delivery_options": ["individual", "chapters", "full_stitch", "highlights"],
        "sample": {"stem": None, "caption_approved": False},
        "batch": {"approved": False},
        "stitch": {"approved": False, "chapters": []},
        "exclude_stems": [],
        "director_recommendation": "",
        "user_notes": "",
        "approved_by_user": False,
        "updated_at": None,
    }


def load_decisions() -> dict:
    if DECISIONS_PATH.exists():
        return json.loads(DECISIONS_PATH.read_text())
    return default_decisions()


def save_decisions(data: dict) -> None:
    DIRECTOR_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    DECISIONS_PATH.write_text(json.dumps(data, indent=2))


def render_brief(items: list[dict]) -> str:
    total_s = total_output_s(items)
    fragments = [i["stem"] for i in items if "fragment" in i["flags"]]
    false_ends = [i["stem"] for i in items if "false_end" in i["flags"]]
    qa_clips = [i["stem"] for i in items if "qa" in i["flags"]]

    lines = [
        "# Director brief",
        "",
        "Read this before proposing delivery format or stitching. **Do not render or stitch until the user confirms.**",
        "",
        f"- **Clips:** {len(items)}",
        f"- **Estimated output (if all included):** {total_s:.0f}s ({total_s / 60:.1f} min)",
        f"- **Auto-flagged fragments (<{FRAGMENT_MAX_S}s):** {', '.join(fragments) or 'none'}",
        f"- **Auto-flagged false ends ('thank you'):** {', '.join(false_ends) or 'none'}",
        f"- **Likely Q&A clips:** {', '.join(qa_clips) or 'none'}",
        "",
        "---",
        "",
        "## Clip inventory (source order)",
        "",
        "| # | Clip | Out | Trim | Flags | Preview |",
        "|---|------|-----|------|-------|---------|",
    ]
    for it in items:
        out = f"{it['output_s']:.1f}s" if it["output_s"] else "—"
        trim = f"{it['trim_pct']}%" if it["trim_pct"] is not None else "—"
        flags = ", ".join(it["flags"]) or "—"
        lines.append(
            f"| {it['order']} | {it['stem']} | {out} | {trim} | {flags} | {it['preview']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Delivery options (discuss with user)",
        "",
        "| Option | Description | When to use |",
        "|--------|-------------|-------------|",
        "| **individual** | Keep each `*_clean.mp4` separate | Social clips, modular posting |",
        "| **chapters** | 3–4 topic videos (~1–3 min each) | Full talk, easier to watch |",
        "| **full_stitch** | One continuous video | Only if user wants single file |",
        "| **highlights** | 60–90s best moments only | Trailer / promo |",
        "",
        "---",
        "",
        "## Director recommendation (agent: fill this in)",
        "",
        "_Suggested delivery format, chapter groupings, clips to exclude, and sample stem for caption approval._",
        "",
        "**Recommended delivery:** ",
        "",
        "**Suggested sample clip for caption review:** ",
        "",
        "**Exclude from stitch:** ",
        "",
        "**Proposed chapters (if delivery = chapters):**",
        "",
        "1. _Chapter title_ — clips: …",
        "2. …",
        "",
        "---",
        "",
        "## Questions for user (agent: ask before executing)",
        "",
        "- [ ] Which delivery option? (individual / chapters / full_stitch / highlights)",
        "- [ ] Confirm clip order or reorder?",
        "- [ ] Exclude flagged fragments?",
        "- [ ] Approve sample clip + caption style before batch?",
        "- [ ] If chapters: approve groupings before `stitch_chapters.py`?",
        "",
        "---",
        "",
        "## After user confirms",
        "",
        "1. Update `edit/director/decisions.json` (`delivery`, `exclude_stems`, `chapters`, approvals)",
        "2. Run `python scripts/director.py apply` to sync `config/chapters.json`",
        "3. Proceed: sample → batch → stitch per gate flags",
        "",
    ])
    return "\n".join(lines)


def cmd_inventory() -> None:
    DIRECTOR_DIR.mkdir(parents=True, exist_ok=True)
    items = build_inventory()
    INVENTORY_PATH.write_text(json.dumps(items, indent=2))
    print(f"inventory → {INVENTORY_PATH} ({len(items)} clips)")


def cmd_brief() -> None:
    if not INVENTORY_PATH.exists():
        cmd_inventory()
    items = json.loads(INVENTORY_PATH.read_text())
    DIRECTOR_DIR.mkdir(parents=True, exist_ok=True)
    BRIEF_PATH.write_text(render_brief(items))
    print(f"brief → {BRIEF_PATH}")


def cmd_init() -> None:
    DIRECTOR_DIR.mkdir(parents=True, exist_ok=True)
    if DECISIONS_PATH.exists():
        print(f"decisions already exist: {DECISIONS_PATH}")
        return
    save_decisions(default_decisions())
    print(f"decisions → {DECISIONS_PATH}")


def cmd_validate() -> None:
    d = load_decisions()
    print(json.dumps({
        "delivery": d.get("delivery"),
        "sample_stem": d.get("sample", {}).get("stem"),
        "caption_approved": d.get("sample", {}).get("caption_approved"),
        "batch_approved": d.get("batch", {}).get("approved"),
        "stitch_approved": d.get("stitch", {}).get("approved"),
        "exclude_count": len(d.get("exclude_stems") or []),
        "chapter_count": len(d.get("stitch", {}).get("chapters") or []),
    }, indent=2))


def cmd_gate(step: str) -> None:
    d = load_decisions()
    if step == "sample":
        # Sample always allowed after transcribe/edl
        print("OK: sample render allowed (caption review)")
        sys.exit(0)
    if step == "batch":
        sample = d.get("sample", {})
        batch = d.get("batch", {})
        if batch.get("approved") and sample.get("caption_approved"):
            print("OK: batch approved")
            sys.exit(0)
        missing = []
        if not sample.get("caption_approved"):
            missing.append("sample.caption_approved")
        if not batch.get("approved"):
            missing.append("batch.approved")
        print(f"BLOCKED: set {', '.join(missing)} in edit/director/decisions.json (or --force)")
        sys.exit(1)
    if step == "stitch":
        chapters = d.get("stitch", {}).get("chapters") or []
        if d.get("stitch", {}).get("approved") and chapters:
            print(f"OK: stitch approved ({len(chapters)} chapters)")
            sys.exit(0)
        print("BLOCKED: set stitch.approved=true and stitch.chapters[] in decisions.json")
        sys.exit(1)
    print(f"unknown gate: {step}")
    sys.exit(2)


def cmd_apply() -> None:
    d = load_decisions()
    chapters = d.get("stitch", {}).get("chapters") or []
    if not chapters:
        sys.exit("No chapters in decisions.json — fill stitch.chapters first")
    payload = {
        "chapters": chapters,
        "exclude_fragments": d.get("exclude_stems") or [],
    }
    CHAPTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHAPTERS_PATH.write_text(json.dumps(payload, indent=2))
    print(f"chapters → {CHAPTERS_PATH}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "inventory":
        cmd_inventory()
    elif cmd == "brief":
        cmd_brief()
    elif cmd == "init":
        cmd_init()
    elif cmd == "validate":
        cmd_validate()
    elif cmd == "gate":
        cmd_gate(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "apply":
        cmd_apply()
    else:
        print(f"unknown command: {cmd}")
        sys.exit(2)


if __name__ == "__main__":
    main()
