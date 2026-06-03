#!/usr/bin/env python3
"""
Video editing studio — full pipeline orchestrator.

  python edit.py raw.mp4
  python edit.py raw.mp4 --overlay caption_burn
  python edit.py raw.mp4 --overlay lower_third --name "Jane Smith" --title "CEO"
  python edit.py raw.mp4 --overlay title_card --title "The Future of AI" --subtitle "Episode 1"
  python edit.py raw.mp4 --grade warm_cinematic --no-filler --preview
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from pipeline.transcribe import transcribe_one
from pipeline.filler_remover import build_edl
from pipeline.render import render_edl
from pipeline.timeline_view import generate_timeline
from pipeline.graphics_builder import build_composition, render_composition
from pipeline.grade import PRESETS as GRADE_PRESETS


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Video editing studio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("video", help="Raw input video file")
    parser.add_argument(
        "--overlay",
        metavar="TEMPLATE",
        help="Motion graphics template: caption_burn | lower_third | title_card | kinetic_text",
    )
    parser.add_argument("--no-filler", action="store_true", help="Skip filler word removal")
    parser.add_argument(
        "--grade",
        default="none",
        choices=list(GRADE_PRESETS),
        help="Color grade preset",
    )
    parser.add_argument("--preview", action="store_true", help="720p preview quality (faster)")
    parser.add_argument("--speakers", type=int, default=1, help="Number of speakers for diarization")
    parser.add_argument("--out", metavar="PATH", help="Output file (default: edit/final.mp4)")
    parser.add_argument("--no-timeline", action="store_true", help="Skip waveform timeline PNG")

    # Template-specific overrides
    parser.add_argument("--name", default="Your Name", help="lower_third: speaker name")
    parser.add_argument("--title", default="Your Title", help="lower_third: title / title_card: title")
    parser.add_argument("--subtitle", default="", help="title_card: subtitle")
    parser.add_argument("--eyebrow", default="", help="title_card: small text above title")
    parser.add_argument("--show-at", type=float, default=1.0, help="lower_third/title_card: start time (s)")
    parser.add_argument("--show-for", type=float, default=4.0, help="lower_third/title_card: hold duration (s)")

    args = parser.parse_args()

    video = Path(args.video).resolve()
    if not video.exists():
        sys.exit(f"Video not found: {video}")

    edit_dir = video.parent / "edit"
    edit_dir.mkdir(exist_ok=True)
    out_path = Path(args.out).resolve() if args.out else edit_dir / "final.mp4"

    # ── 1. Transcribe ─────────────────────────────────────────────────────────
    print(f"\n[1/4] Transcribing {video.name}...")
    transcript = transcribe_one(video, edit_dir, num_speakers=args.speakers)

    # ── 2. Build EDL ──────────────────────────────────────────────────────────
    print("\n[2/4] Building edit decision list...")
    edl = build_edl(
        video=video,
        transcript=transcript,
        edit_dir=edit_dir,
        remove_fillers=not args.no_filler,
    )
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl, indent=2))

    orig = edl["original_duration_s"]
    edited = edl["total_duration_s"]
    saved = edl["time_saved_s"]
    n = len(edl["ranges"])
    pct = (saved / orig * 100) if orig > 0 else 0
    print(f"       {n} segments | {orig:.1f}s → {edited:.1f}s | saved {saved:.1f}s ({pct:.0f}%)")
    print(f"       EDL: {edl_path}")

    if not args.no_timeline:
        try:
            tl_png = edit_dir / "timeline.png"
            generate_timeline(video, edl, tl_png)
            print(f"       Timeline: {tl_png}")
        except Exception as exc:
            print(f"       Timeline skipped ({exc})")

    # ── 3. Render clean video ─────────────────────────────────────────────────
    clean_mp4 = edit_dir / "clean.mp4"
    print(f"\n[3/4] Rendering clean video ({args.grade} grade)...")
    render_edl(edl, clean_mp4, preview=args.preview, grade=args.grade)
    print(f"       Clean video: {clean_mp4}")

    # ── 4. Motion graphics ────────────────────────────────────────────────────
    if not args.overlay:
        print("\n[4/4] No overlay — copying clean video to output")
        shutil.copy(clean_mp4, out_path)
        _done(out_path, orig, edited)
        return

    print(f"\n[4/4] Building motion graphics: {args.overlay}...")
    extra = {
        "NAME": args.name,
        "TITLE": args.title,
        "SUBTITLE": args.subtitle,
        "EYEBROW": args.eyebrow or args.title,
        "START": str(args.show_at),
        "SHOW_DURATION": str(args.show_for),
    }

    try:
        comp_dir = build_composition(
            video_path=clean_mp4,
            transcript=transcript,
            template=args.overlay,
            out_dir=edit_dir / "animations" / args.overlay,
            extra=extra,
        )
        print(f"       Composition: {comp_dir / 'composition.html'}")
        print("       Rendering with HyperFrames (npx hyperframes render)...")
        final_mp4 = render_composition(comp_dir, out_path)
        _done(final_mp4, orig, edited)
    except FileNotFoundError as exc:
        sys.exit(str(exc))
    except RuntimeError as exc:
        print(f"\n  HyperFrames render failed. Falling back to clean video.\n  {exc}")
        shutil.copy(clean_mp4, out_path)
        _done(out_path, orig, edited)


def _done(out_path: Path, orig: float, edited: float) -> None:
    saved = orig - edited
    print(f"\n{'─'*50}")
    print(f"  Done!  {out_path}")
    print(f"  {orig:.1f}s  →  {edited:.1f}s  (saved {saved:.1f}s)")
    print(f"{'─'*50}\n")


if __name__ == "__main__":
    main()
