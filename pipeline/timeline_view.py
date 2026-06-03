"""
Generate a visual timeline PNG showing the waveform and kept/cut regions.

Usage:
  python -m pipeline.timeline_view <video> <edl.json> -o timeline.png
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def generate_timeline(video_path: Path, edl: dict, out_png: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        import librosa
    except ImportError:
        print("  timeline_view: pip install matplotlib librosa numpy to enable")
        return

    wav = out_png.parent / "_tl_audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-vn", "-ar", "22050", "-ac", "1", str(wav)],
        capture_output=True, check=True,
    )

    y, sr = librosa.load(str(wav), sr=22050, mono=True)
    total_s = len(y) / sr
    times = np.linspace(0, total_s, len(y))

    fig, ax = plt.subplots(figsize=(18, 3), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    ax.fill_between(times, y, -y, color="#3a3a3a", linewidth=0)

    for rng in edl.get("ranges", []):
        ax.axvspan(rng["start"], rng["end"], alpha=0.35, color="#00e676", linewidth=0)

    ax.set_xlim(0, total_s)
    ax.set_ylim(-1.05, 1.05)
    ax.tick_params(colors="#666", labelsize=8)
    ax.set_xlabel("seconds", color="#666", fontsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#222")

    orig = edl.get("original_duration_s", total_s)
    edited = edl.get("total_duration_s", total_s)
    saved = edl.get("time_saved_s", 0)
    pct = (saved / orig * 100) if orig > 0 else 0
    fig.text(
        0.01, 0.92,
        f"  {video_path.name}  ·  {orig:.1f}s → {edited:.1f}s  ·  saved {saved:.1f}s ({pct:.0f}%)",
        color="#ccc", fontsize=9, va="top",
    )

    plt.tight_layout(pad=0.4)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_png), dpi=130, bbox_inches="tight", facecolor="#0d0d0d")
    plt.close()
    wav.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate timeline visualization")
    parser.add_argument("video")
    parser.add_argument("edl", help="Path to edl.json")
    parser.add_argument("-o", "--out", default="timeline.png")
    args = parser.parse_args()

    edl = json.loads(Path(args.edl).read_text())
    generate_timeline(Path(args.video), edl, Path(args.out))
    print(f"Timeline saved: {args.out}")


if __name__ == "__main__":
    main()
