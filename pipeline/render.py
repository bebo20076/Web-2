"""
Render an EDL JSON to a clean MP4 using FFmpeg.

Pipeline:
  1. Per-segment extraction  — grade + scale + 30ms audio fades
  2. Lossless concatenation  — segments → base.mp4 via concat demuxer
  3. Loudness normalization   — -14 LUFS / -1 dBTP (YouTube/TikTok/IG standard)

Usage:
  python -m pipeline.render edl.json -o clean.mp4
  python -m pipeline.render edl.json -o preview.mp4 --preview
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from .grade import PRESETS as GRADE_PRESETS

CRF_FINAL = 20
CRF_PREVIEW = 22
SCALE_FINAL = "1920:1080"
SCALE_PREVIEW = "1280:720"
AUDIO_FADE_S = 0.03   # 30ms fades at every segment boundary


def _run(cmd: list, label: str = "") -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tag = f" ({label})" if label else ""
        raise RuntimeError(f"FFmpeg failed{tag}:\n{result.stderr[-2000:]}")


def _extract_segment(
    source: str,
    start: float,
    end: float,
    out: Path,
    scale: str,
    crf: int,
    grade_filter: str,
) -> None:
    duration = end - start

    vf_parts = [f"scale={scale}:force_original_aspect_ratio=decrease"]
    if grade_filter:
        vf_parts.append(grade_filter)
    vf = ",".join(vf_parts)

    af = (
        f"afade=t=in:ss=0:d={AUDIO_FADE_S},"
        f"afade=t=out:st={max(0.0, duration - AUDIO_FADE_S)}:d={AUDIO_FADE_S}"
    )

    _run([
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", source,
        "-t", str(duration),
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out),
    ], label=f"seg {out.stem}")


def _concat(segment_paths: list[Path], out: Path) -> None:
    list_file = out.parent / "_concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in segment_paths)
    )
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", str(out),
    ], label="concat")
    list_file.unlink(missing_ok=True)


def _loudnorm(inp: Path, out: Path, crf: int) -> None:
    _run([
        "ffmpeg", "-y", "-i", str(inp),
        "-filter_complex", "[0:a]loudnorm=I=-14:TP=-1:LRA=11[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out),
    ], label="loudnorm")


def render_edl(
    edl: dict,
    out_path: Path,
    preview: bool = False,
    grade: str = "none",
) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    crf = CRF_PREVIEW if preview else CRF_FINAL
    scale = SCALE_PREVIEW if preview else SCALE_FINAL
    grade_filter = GRADE_PRESETS.get(grade, "")

    seg_dir = out_path.parent / "_segments"
    seg_dir.mkdir(exist_ok=True)

    segment_paths: list[Path] = []
    for i, rng in enumerate(edl["ranges"]):
        source_path = edl["sources"][rng["source"]]
        seg_out = seg_dir / f"seg_{i:04d}.mp4"
        print(f"       Segment {i+1}/{len(edl['ranges'])}: {rng['start']:.2f}s–{rng['end']:.2f}s")
        _extract_segment(source_path, rng["start"], rng["end"], seg_out, scale, crf, grade_filter)
        segment_paths.append(seg_out)

    base_mp4 = out_path.parent / "_base.mp4"
    print("       Concatenating segments...")
    _concat(segment_paths, base_mp4)

    print("       Normalizing loudness (-14 LUFS)...")
    _loudnorm(base_mp4, out_path, crf)

    base_mp4.unlink(missing_ok=True)
    for p in segment_paths:
        p.unlink(missing_ok=True)
    (seg_dir / "_concat.txt").unlink(missing_ok=True)
    try:
        seg_dir.rmdir()
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Render EDL to MP4")
    parser.add_argument("edl", help="Path to edl.json")
    parser.add_argument("-o", "--out", required=True, help="Output MP4 path")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--grade", default="none", choices=list(GRADE_PRESETS))
    args = parser.parse_args()

    edl = json.loads(Path(args.edl).read_text())
    render_edl(edl, Path(args.out), preview=args.preview, grade=args.grade)
    print(f"Rendered: {args.out}")


if __name__ == "__main__":
    main()
