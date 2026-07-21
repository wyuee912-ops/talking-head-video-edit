#!/usr/bin/env python3
"""Compose a vertical (9:16) demo + talking-head split for TikTok / IG.

Reverse-engineered from CapCut export `0716(1).mov` (2160×3840):
  black pad → cover-fit demo → cover-fit head → black pad.

Usage:
    # Dump resolved pixel geometry
    python helpers/compose_split.py geometry --preset capcut_0716_vertical

    # Still-frame verify
    python helpers/compose_split.py still \\
        --demo demo.mov --head head.mov --t 5.0 -o verify.png

    # Full video (demo on top while it lasts; head stays in bottom slot;
    # after demo ends the top slot goes black — CapCut track1 tail)
    python helpers/compose_split.py render \\
        --demo demo.mov --head head.mov -o out.mp4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


@dataclass
class SplitPreset:
    """Pixel layout for a vertical split composite.

    All sizes are in output-canvas pixels (author canvas). Sources are
    cover-fitted into their slots (full height kept; left/right cropped when
    the source is wider than the slot — typical for 16:9 → 9:16 bands).
    """

    name: str
    canvas_w: int
    canvas_h: int
    pad_top: int
    demo_h: int
    head_h: int
    pad_bottom: int
    notes: str = ""

    def __post_init__(self) -> None:
        used = self.pad_top + self.demo_h + self.head_h + self.pad_bottom
        if used != self.canvas_h:
            raise ValueError(
                f"{self.name}: pads+slots={used} != canvas_h={self.canvas_h}"
            )


PRESETS: dict[str, SplitPreset] = {
    "capcut_0716_vertical": SplitPreset(
        name="capcut_0716_vertical",
        canvas_w=2160,
        canvas_h=3840,
        pad_top=301,
        demo_h=1682,  # y=301..1983
        head_h=1575,  # y=1983..3558
        pad_bottom=282,  # y=3558..3840
        notes=(
            "9:16 TikTok/IG split from CapCut export 0716(1).mov. "
            "Not 50/50 — demo slot taller. Verified MAE≈1.8 on head vs ref @ t=5s. "
            "After demo ends (~53s): top → black; head stays letterboxed in bottom slot."
        ),
    ),
}


@dataclass
class SlotGeometry:
    """Cover-fit crop of a source into one output slot."""

    # Source crop (pixels on the input file)
    src_x: int
    src_y: int
    src_w: int
    src_h: int
    # Destination rect on the canvas
    dst_x: int
    dst_y: int
    dst_w: int
    dst_h: int


@dataclass
class SplitGeometry:
    canvas_w: int
    canvas_h: int
    pad_top: int
    pad_bottom: int
    demo: SlotGeometry
    head: SlotGeometry

    def as_dict(self) -> dict:
        return {
            "canvas_w": self.canvas_w,
            "canvas_h": self.canvas_h,
            "pad_top": self.pad_top,
            "pad_bottom": self.pad_bottom,
            "demo": asdict(self.demo),
            "head": asdict(self.head),
        }


def cover_fit_crop(
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
    *,
    dst_x: int,
    dst_y: int,
) -> SlotGeometry:
    """Center-crop source so it cover-fills the destination rect."""
    src_ar = src_w / src_h
    dst_ar = dst_w / dst_h
    if src_ar > dst_ar:
        # Source wider → keep full height, crop left/right
        crop_h = src_h
        crop_w = int(round(src_h * dst_ar))
        crop_x = (src_w - crop_w) // 2
        crop_y = 0
    else:
        # Source taller → keep full width, crop top/bottom
        crop_w = src_w
        crop_h = int(round(src_w / dst_ar))
        crop_x = 0
        crop_y = (src_h - crop_h) // 2
    return SlotGeometry(
        src_x=crop_x,
        src_y=crop_y,
        src_w=crop_w,
        src_h=crop_h,
        dst_x=dst_x,
        dst_y=dst_y,
        dst_w=dst_w,
        dst_h=dst_h,
    )


def resolve_geometry(
    preset: SplitPreset,
    demo_w: int,
    demo_h: int,
    head_w: int,
    head_h: int,
) -> SplitGeometry:
    demo_y = preset.pad_top
    head_y = preset.pad_top + preset.demo_h
    return SplitGeometry(
        canvas_w=preset.canvas_w,
        canvas_h=preset.canvas_h,
        pad_top=preset.pad_top,
        pad_bottom=preset.pad_bottom,
        demo=cover_fit_crop(
            demo_w, demo_h, preset.canvas_w, preset.demo_h,
            dst_x=0, dst_y=demo_y,
        ),
        head=cover_fit_crop(
            head_w, head_h, preset.canvas_w, preset.head_h,
            dst_x=0, dst_y=head_y,
        ),
    )


# ---------------------------------------------------------------------------
# Probe / IO
# ---------------------------------------------------------------------------


def ffprobe_video(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    data = json.loads(subprocess.check_output(cmd, text=True))
    stream = data["streams"][0]
    dur = float(stream.get("duration") or data["format"]["duration"])
    num, den = stream["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": fps,
        "duration": dur,
    }


def extract_frame(path: Path, t: float, out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", str(out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------


def _paste_cover(canvas: Image.Image, src: Image.Image, slot: SlotGeometry) -> None:
    box = (slot.src_x, slot.src_y, slot.src_x + slot.src_w, slot.src_y + slot.src_h)
    cropped = src.crop(box).resize((slot.dst_w, slot.dst_h), Image.LANCZOS)
    canvas.paste(cropped, (slot.dst_x, slot.dst_y))


def compose_still(
    demo_frame: Path,
    head_frame: Path,
    geom: SplitGeometry,
    out: Path,
    *,
    demo_active: bool = True,
) -> None:
    """PIL still composite — good for layout verify."""
    canvas = Image.new("RGB", (geom.canvas_w, geom.canvas_h), (0, 0, 0))
    if demo_active:
        demo = Image.open(demo_frame).convert("RGB")
        _paste_cover(canvas, demo, geom.demo)
    head = Image.open(head_frame).convert("RGB")
    _paste_cover(canvas, head, geom.head)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def compose_video(
    demo: Path,
    head: Path,
    geom: SplitGeometry,
    out: Path,
    *,
    duration: float | None = None,
    head_offset: float = 0.0,
    demo_offset: float = 0.0,
    fps: float | None = None,
    crf: int = 18,
    x264_preset: str = "fast",
    audio: str = "head",  # head | demo | both | none
) -> None:
    """ffmpeg vertical split. Demo ends → top slot black; head keeps playing."""
    demo_meta = ffprobe_video(demo)
    head_meta = ffprobe_video(head)
    out_fps = fps or 30.0

    demo_avail = max(0.0, demo_meta["duration"] - demo_offset)
    head_avail = max(0.0, head_meta["duration"] - head_offset)
    out_dur = duration if duration is not None else max(demo_avail, head_avail)
    if out_dur <= 0:
        raise SystemExit("duration ≤ 0 after offsets")

    d, h = geom.demo, geom.head
    # [0] demo  [1] head
    # Cover-fit each into its slot, pad onto black canvas, overlay head below demo.
    filter_complex = (
        f"color=c=black:s={geom.canvas_w}x{geom.canvas_h}:d={out_dur:.6f}:r={out_fps}[bg];"
        f"[0:v]trim=start=0:duration={demo_avail:.6f},setpts=PTS-STARTPTS,"
        f"crop={d.src_w}:{d.src_h}:{d.src_x}:{d.src_y},"
        f"scale={d.dst_w}:{d.dst_h}:flags=lanczos,fps={out_fps},"
        f"format=yuv420p[demo];"
        f"[1:v]trim=start=0:duration={out_dur:.6f},setpts=PTS-STARTPTS,"
        f"crop={h.src_w}:{h.src_h}:{h.src_x}:{h.src_y},"
        f"scale={h.dst_w}:{h.dst_h}:flags=lanczos,fps={out_fps},"
        f"format=yuv420p[head];"
        f"[bg][demo]overlay={d.dst_x}:{d.dst_y}:eof_action=pass:shortest=0[tmp];"
        f"[tmp][head]overlay={h.dst_x}:{h.dst_y}:eof_action=pass:shortest=0,"
        f"format=yuv420p[vout]"
    )

    if audio == "both":
        filter_complex += (
            f";[0:a]atrim=start=0:duration={min(demo_avail, out_dur):.6f},"
            f"asetpts=PTS-STARTPTS,volume=0.3,apad=whole_dur={out_dur:.6f}[a0];"
            f"[1:a]atrim=start=0:duration={out_dur:.6f},"
            f"asetpts=PTS-STARTPTS,volume=1.0[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
        maps = ["-map", "[vout]", "-map", "[aout]"]
        audio_args = ["-c:a", "aac", "-b:a", "192k"]
    elif audio == "head":
        maps = ["-map", "[vout]", "-map", "1:a:0"]
        audio_args = ["-c:a", "aac", "-b:a", "192k"]
    elif audio == "demo":
        maps = ["-map", "[vout]", "-map", "0:a:0"]
        audio_args = ["-c:a", "aac", "-b:a", "192k"]
    else:
        maps = ["-map", "[vout]"]
        audio_args = ["-an"]

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{demo_offset:.3f}", "-t", f"{out_dur:.3f}", "-i", str(demo),
        "-ss", f"{head_offset:.3f}", "-t", f"{out_dur:.3f}", "-i", str(head),
        "-filter_complex", filter_complex,
        *maps,
        "-c:v", "libx264", "-preset", x264_preset, "-crf", str(crf),
        "-r", str(out_fps),
        "-pix_fmt", "yuv420p",
        *audio_args,
        "-movflags", "+faststart",
        "-t", f"{out_dur:.3f}",
        str(out),
    ]
    print("ffmpeg compose_split →", out)
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def get_preset(name: str) -> SplitPreset:
    if name not in PRESETS:
        known = ", ".join(PRESETS)
        raise SystemExit(f"unknown preset {name!r}; known: {known}")
    return PRESETS[name]


def parse_wh(s: str) -> tuple[int, int]:
    w, h = s.lower().split("x")
    return int(w), int(h)


def cmd_geometry(args: argparse.Namespace) -> None:
    preset = get_preset(args.preset)
    dw, dh = parse_wh(args.demo_source) if args.demo_source else (3840, 2160)
    hw, hh = parse_wh(args.head_source) if args.head_source else (3840, 2160)
    geom = resolve_geometry(preset, dw, dh, hw, hh)
    print(json.dumps({"preset": preset.name, "notes": preset.notes, **geom.as_dict()}, indent=2))


def cmd_still(args: argparse.Namespace) -> None:
    preset = get_preset(args.preset)
    demo = Path(args.demo)
    head = Path(args.head)
    out = Path(args.out)
    demo_meta = ffprobe_video(demo)
    head_meta = ffprobe_video(head)
    geom = resolve_geometry(
        preset,
        demo_meta["width"], demo_meta["height"],
        head_meta["width"], head_meta["height"],
    )
    print("geometry:", json.dumps(geom.as_dict()))

    t = args.t
    demo_active = (t + args.demo_offset) < demo_meta["duration"]
    with tempfile.TemporaryDirectory(prefix="split_still_") as td:
        dframe = Path(td) / "demo.png"
        hframe = Path(td) / "head.png"
        if demo_active:
            extract_frame(demo, t + args.demo_offset, dframe)
        else:
            # unused; compose_still skips demo paste
            Image.new("RGB", (demo_meta["width"], demo_meta["height"]), (0, 0, 0)).save(dframe)
        extract_frame(head, t + args.head_offset, hframe)
        compose_still(dframe, hframe, geom, out, demo_active=demo_active)
    print(f"wrote {out}")


def cmd_render(args: argparse.Namespace) -> None:
    preset = get_preset(args.preset)
    demo = Path(args.demo)
    head = Path(args.head)
    out = Path(args.out)
    demo_meta = ffprobe_video(demo)
    head_meta = ffprobe_video(head)
    geom = resolve_geometry(
        preset,
        demo_meta["width"], demo_meta["height"],
        head_meta["width"], head_meta["height"],
    )
    print("geometry:", json.dumps(geom.as_dict()))
    compose_video(
        demo, head, geom, out,
        duration=args.duration,
        head_offset=args.head_offset,
        demo_offset=args.demo_offset,
        fps=args.fps,
        crf=args.crf,
        x264_preset=args.x264_preset,
        audio=args.audio,
    )
    print(f"wrote {out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("geometry", help="print resolved pixel geometry")
    g.add_argument("--preset", default="capcut_0716_vertical")
    g.add_argument("--demo-source", default="3840x2160")
    g.add_argument("--head-source", default="3840x2160")
    g.set_defaults(func=cmd_geometry)

    s = sub.add_parser("still", help="composite one still frame")
    s.add_argument("--preset", default="capcut_0716_vertical")
    s.add_argument("--demo", required=True)
    s.add_argument("--head", required=True)
    s.add_argument("--t", type=float, default=5.0)
    s.add_argument("--demo-offset", type=float, default=0.0)
    s.add_argument("--head-offset", type=float, default=0.0)
    s.add_argument("-o", "--out", required=True)
    s.set_defaults(func=cmd_still)

    r = sub.add_parser("render", help="composite full video")
    r.add_argument("--preset", default="capcut_0716_vertical")
    r.add_argument("--demo", required=True)
    r.add_argument("--head", required=True)
    r.add_argument("--duration", type=float, default=None)
    r.add_argument("--demo-offset", type=float, default=0.0)
    r.add_argument("--head-offset", type=float, default=0.0)
    r.add_argument("--fps", type=float, default=30.0)
    r.add_argument("--crf", type=int, default=18)
    r.add_argument("--x264-preset", default="fast")
    r.add_argument(
        "--audio",
        choices=["both", "demo", "head", "none"],
        default="head",
        help="head=VO only (default)",
    )
    r.add_argument("-o", "--out", required=True)
    r.set_defaults(func=cmd_render)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
