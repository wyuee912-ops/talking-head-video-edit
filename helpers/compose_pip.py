#!/usr/bin/env python3
"""Compose a talking-head PiP (rounded-rect) over a demo / screen-recording base.

Reverse-engineered from CapCut draft `0716` (export 0716(2).mov):
  material crop → contain-fit into scaled layer → rectangle mask → overlay.

Usage:
    # Still-frame verify (writes PNG)
    python helpers/compose_pip.py still \\
        --demo demo.mov --head head.mov --t 5.0 -o verify.png

    # Full video (PiP for whole duration, or until --duration)
    python helpers/compose_pip.py render \\
        --demo demo.mov --head head.mov -o out.mp4

    # Use / override the CapCut 0716 preset
    python helpers/compose_pip.py render --preset capcut_0716 \\
        --demo demo.mov --head head.mov -o out.mp4

    # Dump resolved pixel geometry for a canvas size
    python helpers/compose_pip.py geometry --preset capcut_0716 --canvas 3840x2160
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# Presets (normalized CapCut-space params)
# ---------------------------------------------------------------------------

@dataclass
class PipPreset:
    """CapCut-normalized PiP layout.

    Coordinate conventions (CapCut draft_info.json):
      - transform x/y: offset of layer center from canvas center, in half-canvas units.
        +x = right, +y = up.
      - scale: layer size as a fraction of canvas (before mask).
      - material_crop: normalized source rect (fractions of source W/H).
      - mask width/height: fraction of the *contain-fitted* cropped content.
      - mask centerX/Y: offset of mask center from content center, in half-content units.
        +centerX = right, +centerY = up.
      - round_corner: CapCut roundCorner; pixel radius = round_corner * min(pip_w, pip_h) / 2.
    """

    name: str
    scale: float
    transform_x: float
    transform_y: float
    material_crop: dict  # ulx, uly, urx, lly  (normalized 0-1)
    mask_width: float
    mask_height: float
    mask_center_x: float
    mask_center_y: float
    round_corner: float
    # Project canvas the params were authored against (CapCut stores 1920x1080;
    # exports are often 2×). Geometry scales with the output canvas.
    author_canvas: tuple[int, int] = (1920, 1080)
    notes: str = ""


PRESETS: dict[str, PipPreset] = {
    "capcut_0716": PipPreset(
        name="capcut_0716",
        scale=0.3206586026808049,
        transform_x=0.625,
        transform_y=-0.5474925397127282,
        material_crop={
            "ulx": 0.2677320397418478,
            "uly": 0.19455672554347825,
            "urx": 0.8084270974864131,
            "lly": 0.8012992527173913,
        },
        mask_width=0.6939104603293413,
        mask_height=0.8303271757207469,
        mask_center_x=0.040438919127515495,
        mask_center_y=0.09337342337673915,
        round_corner=0.4515625,
        notes=(
            "Bottom-right rounded talking-head over demo. "
            "From CapCut draft 0716 track1 seg0 + material crop on 7月20日 (1).mov. "
            "Verified MAE≈2 vs export 0716(2).mov @ t=5s."
        ),
    ),
}


@dataclass
class PipGeometry:
    """Resolved pixel geometry for one canvas size."""

    canvas_w: int
    canvas_h: int
    # Source crop (pixels on the talking-head file)
    src_x: float
    src_y: float
    src_w: float
    src_h: float
    # PiP placement on the output canvas
    pip_x: float
    pip_y: float
    pip_w: float
    pip_h: float
    radius: float

    def as_ints(self) -> dict[str, int]:
        return {
            "src_x": int(round(self.src_x)),
            "src_y": int(round(self.src_y)),
            "src_w": int(round(self.src_w)),
            "src_h": int(round(self.src_h)),
            "pip_x": int(round(self.pip_x)),
            "pip_y": int(round(self.pip_y)),
            "pip_w": int(round(self.pip_w)),
            "pip_h": int(round(self.pip_h)),
            "radius": max(1, int(round(self.radius))),
        }


def resolve_geometry(
    preset: PipPreset,
    canvas_w: int,
    canvas_h: int,
    source_w: int,
    source_h: int,
) -> PipGeometry:
    """Map CapCut-normalized preset → pixel crop + PiP box on `canvas_*`."""
    mc = preset.material_crop
    mat_ulx, mat_uly = mc["ulx"], mc["uly"]
    mat_w = mc["urx"] - mc["ulx"]
    mat_h = mc["lly"] - mc["uly"]

    # Cropped content aspect (pixels)
    crop_ar = (mat_w * source_w) / (mat_h * source_h)

    # Layer = canvas * scale ( CapCut scale is relative to author canvas proportions;
    # for same-aspect outputs this is just a fraction of the output canvas. )
    layer_w = canvas_w * preset.scale
    layer_h = canvas_h * preset.scale

    # Contain-fit the cropped content into the layer
    fit_h = layer_h
    fit_w = fit_h * crop_ar
    if fit_w > layer_w:
        fit_w = layer_w
        fit_h = fit_w / crop_ar

    # Layer center from transform (+y up)
    lcx = canvas_w / 2 + preset.transform_x * (canvas_w / 2)
    lcy = canvas_h / 2 - preset.transform_y * (canvas_h / 2)

    # Mask window inside the fitted content
    mw = fit_w * preset.mask_width
    mh = fit_h * preset.mask_height
    mcx = lcx + preset.mask_center_x * (fit_w / 2)
    mcy = lcy - preset.mask_center_y * (fit_h / 2)

    # Source crop = material crop, then mask window within it
    # mask centerY > 0 → mask center above content center → top shrinks
    m_left = 0.5 + preset.mask_center_x / 2 - preset.mask_width / 2
    m_top = 0.5 - preset.mask_center_y / 2 - preset.mask_height / 2
    src_x = (mat_ulx + m_left * mat_w) * source_w
    src_y = (mat_uly + m_top * mat_h) * source_h
    src_w = preset.mask_width * mat_w * source_w
    src_h = preset.mask_height * mat_h * source_h

    radius = preset.round_corner * min(mw, mh) / 2

    return PipGeometry(
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        src_x=src_x,
        src_y=src_y,
        src_w=src_w,
        src_h=src_h,
        pip_x=mcx - mw / 2,
        pip_y=mcy - mh / 2,
        pip_w=mw,
        pip_h=mh,
        radius=radius,
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
    raw = subprocess.check_output(cmd, text=True)
    data = json.loads(raw)
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


def make_rounded_mask(w: int, h: int, radius: int, out: Path) -> None:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    mask.save(out)


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------


def compose_still(
    demo_frame: Path,
    head_frame: Path,
    geom: PipGeometry,
    out: Path,
) -> None:
    """PIL still composite — good for layout verify."""
    g = geom.as_ints()
    demo = Image.open(demo_frame).convert("RGBA")
    head = Image.open(head_frame).convert("RGBA")
    if demo.size != (geom.canvas_w, geom.canvas_h):
        demo = demo.resize((geom.canvas_w, geom.canvas_h), Image.LANCZOS)

    box = (g["src_x"], g["src_y"], g["src_x"] + g["src_w"], g["src_y"] + g["src_h"])
    cropped = head.crop(box).resize((g["pip_w"], g["pip_h"]), Image.LANCZOS)
    mask = Image.new("L", (g["pip_w"], g["pip_h"]), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, g["pip_w"] - 1, g["pip_h"] - 1], radius=g["radius"], fill=255
    )
    cropped.putalpha(mask)
    demo.paste(cropped, (g["pip_x"], g["pip_y"]), cropped)
    out.parent.mkdir(parents=True, exist_ok=True)
    demo.convert("RGB").save(out)


def _rounded_rect_alpha_expr(w: int, h: int, r: int) -> str:
    """ffmpeg geq alpha expression for a filled rounded rect (0..255)."""
    # Inside the axis-aligned body → 255; in corner circles → 255 if inside radius; else 0.
    # X,Y are pixel coords; W,H are frame size (geq provides them).
    return (
        f"if(lte(X\\,{r})*lte(Y\\,{r})\\,"
        f"if(lte(hypot({r}-X\\,{r}-Y)\\,{r})\\,255\\,0)\\,"
        f"if(gte(X\\,{w-r-1})*lte(Y\\,{r})\\,"
        f"if(lte(hypot(X-({w-1-r})\\,{r}-Y)\\,{r})\\,255\\,0)\\,"
        f"if(lte(X\\,{r})*gte(Y\\,{h-r-1})\\,"
        f"if(lte(hypot({r}-X\\,Y-({h-1-r}))\\,{r})\\,255\\,0)\\,"
        f"if(gte(X\\,{w-r-1})*gte(Y\\,{h-r-1})\\,"
        f"if(lte(hypot(X-({w-1-r})\\,Y-({h-1-r}))\\,{r})\\,255\\,0)\\,"
        f"255))))"
    )


def compose_video(
    demo: Path,
    head: Path,
    geom: PipGeometry,
    out: Path,
    *,
    duration: float | None = None,
    head_offset: float = 0.0,
    demo_offset: float = 0.0,
    fps: float | None = None,
    crf: int = 18,
    preset: str = "fast",
    audio: str = "both",  # both | demo | head | none
) -> None:
    """ffmpeg composite with rounded-rect alpha mask (geq, no extra inputs).

    Audio: `both` amix'es demo+head (head typically carries VO); `head` / `demo`
    pick one track; `none` drops audio.
    """
    g = geom.as_ints()
    demo_meta = ffprobe_video(demo)
    head_meta = ffprobe_video(head)
    out_fps = fps or demo_meta["fps"]
    out_dur = duration
    if out_dur is None:
        out_dur = min(
            demo_meta["duration"] - demo_offset,
            head_meta["duration"] - head_offset,
        )
    if out_dur <= 0:
        raise SystemExit("duration ≤ 0 after offsets")

    out.parent.mkdir(parents=True, exist_ok=True)

    alpha = _rounded_rect_alpha_expr(g["pip_w"], g["pip_h"], g["radius"])
    # [0] demo  [1] head
    # crop → scale → set alpha via geq → overlay
    filter_complex = (
        f"[1:v]crop={g['src_w']}:{g['src_h']}:{g['src_x']}:{g['src_y']},"
        f"scale={g['pip_w']}:{g['pip_h']}:flags=lanczos,format=rgba,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{alpha}'[pip];"
        f"[0:v]scale={geom.canvas_w}:{geom.canvas_h}:flags=lanczos[base];"
        f"[base][pip]overlay={g['pip_x']}:{g['pip_y']}:format=auto,format=yuv420p[vout]"
    )

    maps: list[str]
    if audio == "both":
        filter_complex += (
            f";[0:a]volume=0.3[a0];[1:a]volume=1.0[a1];"
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

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{demo_offset:.3f}", "-t", f"{out_dur:.3f}", "-i", str(demo),
        "-ss", f"{head_offset:.3f}", "-t", f"{out_dur:.3f}", "-i", str(head),
        "-filter_complex", filter_complex,
        *maps,
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-r", str(out_fps),
        "-pix_fmt", "yuv420p",
        *audio_args,
        "-movflags", "+faststart",
        "-t", f"{out_dur:.3f}",
        str(out),
    ]
    print("ffmpeg compose_pip →", out)
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def get_preset(name: str) -> PipPreset:
    if name not in PRESETS:
        known = ", ".join(PRESETS)
        raise SystemExit(f"unknown preset {name!r}; known: {known}")
    return PRESETS[name]


def parse_canvas(s: str) -> tuple[int, int]:
    w, h = s.lower().split("x")
    return int(w), int(h)


def cmd_geometry(args: argparse.Namespace) -> None:
    preset = get_preset(args.preset)
    cw, ch = parse_canvas(args.canvas)
    sw, sh = parse_canvas(args.source) if args.source else (cw, ch)
    geom = resolve_geometry(preset, cw, ch, sw, sh)
    print(json.dumps({"preset": preset.name, "notes": preset.notes, **asdict(geom), "ints": geom.as_ints()}, indent=2))


def cmd_still(args: argparse.Namespace) -> None:
    preset = get_preset(args.preset)
    demo = Path(args.demo)
    head = Path(args.head)
    out = Path(args.out)
    demo_meta = ffprobe_video(demo)
    head_meta = ffprobe_video(head)
    cw, ch = (parse_canvas(args.canvas) if args.canvas
              else (demo_meta["width"], demo_meta["height"]))
    geom = resolve_geometry(preset, cw, ch, head_meta["width"], head_meta["height"])
    print("geometry ints:", geom.as_ints())

    with tempfile.TemporaryDirectory(prefix="pip_still_") as td:
        dframe = Path(td) / "demo.png"
        hframe = Path(td) / "head.png"
        extract_frame(demo, args.t + args.demo_offset, dframe)
        extract_frame(head, args.t + args.head_offset, hframe)
        compose_still(dframe, hframe, geom, out)
    print(f"wrote {out}")


def cmd_render(args: argparse.Namespace) -> None:
    preset = get_preset(args.preset)
    demo = Path(args.demo)
    head = Path(args.head)
    out = Path(args.out)
    demo_meta = ffprobe_video(demo)
    head_meta = ffprobe_video(head)
    cw, ch = (parse_canvas(args.canvas) if args.canvas
              else (demo_meta["width"], demo_meta["height"]))
    geom = resolve_geometry(preset, cw, ch, head_meta["width"], head_meta["height"])
    print("geometry ints:", geom.as_ints())
    compose_video(
        demo, head, geom, out,
        duration=args.duration,
        head_offset=args.head_offset,
        demo_offset=args.demo_offset,
        fps=args.fps,
        crf=args.crf,
        preset=args.x264_preset,
        audio=args.audio,
    )
    print(f"wrote {out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("geometry", help="print resolved pixel geometry")
    g.add_argument("--preset", default="capcut_0716")
    g.add_argument("--canvas", default="3840x2160")
    g.add_argument("--source", default=None, help="source WxH (default=canvas)")
    g.set_defaults(func=cmd_geometry)

    s = sub.add_parser("still", help="composite one still frame")
    s.add_argument("--preset", default="capcut_0716")
    s.add_argument("--demo", required=True)
    s.add_argument("--head", required=True)
    s.add_argument("--t", type=float, default=5.0)
    s.add_argument("--demo-offset", type=float, default=0.0)
    s.add_argument("--head-offset", type=float, default=0.0)
    s.add_argument("--canvas", default=None, help="WxH; default=demo size")
    s.add_argument("-o", "--out", required=True)
    s.set_defaults(func=cmd_still)

    r = sub.add_parser("render", help="composite full video")
    r.add_argument("--preset", default="capcut_0716")
    r.add_argument("--demo", required=True)
    r.add_argument("--head", required=True)
    r.add_argument("--duration", type=float, default=None)
    r.add_argument("--demo-offset", type=float, default=0.0)
    r.add_argument("--head-offset", type=float, default=0.0)
    r.add_argument("--canvas", default=None)
    r.add_argument("--fps", type=float, default=None)
    r.add_argument("--crf", type=int, default=18)
    r.add_argument("--x264-preset", default="fast")
    r.add_argument("--audio", choices=["both", "demo", "head", "none"], default="head",
                   help="head=VO only (default); both=mix demo low+head")
    r.add_argument("-o", "--out", required=True)
    r.set_defaults(func=cmd_render)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
