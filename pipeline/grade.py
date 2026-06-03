"""
FFmpeg video filter chains for color grading presets.

Usage:
  python -m pipeline.grade <input> <output> --preset warm_cinematic
"""
import argparse
import subprocess
from pathlib import Path

PRESETS: dict[str, str] = {
    "none": "",
    "warm_cinematic": (
        "curves=r='0/0 0.5/0.56 1/1':g='0/0 0.5/0.50 1/0.96':b='0/0 0.5/0.46 1/0.90',"
        "eq=contrast=1.05:brightness=0.02:saturation=1.15"
    ),
    "cool_corporate": (
        "curves=r='0/0.02 1/0.96':g='0/0 1/1':b='0/0.05 1/1',"
        "eq=contrast=1.1:saturation=0.95"
    ),
    "vibrant_social": (
        "eq=contrast=1.1:brightness=0.02:saturation=1.4,"
        "curves=r='0/0 0.5/0.55 1/1'"
    ),
    "matte": (
        "curves=r='0/0.05 1/0.95':g='0/0.05 1/0.95':b='0/0.05 1/0.95',"
        "eq=contrast=0.98:saturation=1.1"
    ),
    "cinema_scope": (
        "crop=iw:ih*0.75:0:ih*0.125,"
        "curves=r='0/0 0.5/0.53 1/0.97':g='0/0 0.5/0.51 1/0.97':b='0/0 0.5/0.48 1/0.92',"
        "eq=contrast=1.08:saturation=1.1"
    ),
}


def grade(input_path: Path, output_path: Path, preset: str = "warm_cinematic") -> None:
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Available: {list(PRESETS)}")
    vf = PRESETS[preset]
    if not vf:
        import shutil
        shutil.copy(input_path, output_path)
        return
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vf", vf, "-c:a", "copy",
            "-c:v", "libx264", "-preset", "slow", "-crf", "20",
            str(output_path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Grade failed:\n{result.stderr[-2000:]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply color grade to video")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--preset", default="warm_cinematic", choices=list(PRESETS))
    args = parser.parse_args()
    grade(Path(args.input), Path(args.output), preset=args.preset)
    print(f"Graded ({args.preset}): {args.output}")


if __name__ == "__main__":
    main()
