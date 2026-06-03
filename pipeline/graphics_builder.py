"""
Build HyperFrames composition HTML from a template, injecting:
  - The clean video file path
  - Caption timing data from the word-level transcript
  - Video duration

Templates live in graphics/templates/*.html and use {{PLACEHOLDER}} syntax.

Usage:
  from pipeline.graphics_builder import build_composition, render_composition
"""
import json
import subprocess
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "graphics" / "templates"


def _group_captions(words: list[dict], chunk_size: int = 2) -> list[dict]:
    """Group word-level timestamps into N-word caption chunks (uppercase)."""
    captions = []
    for i in range(0, len(words), chunk_size):
        chunk = words[i : i + chunk_size]
        captions.append({
            "text": " ".join(w["text"].upper() for w in chunk),
            "start": round(chunk[0]["start"], 3),
            "end": round(chunk[-1]["end"], 3),
        })
    return captions


def build_composition(
    video_path: Path,
    transcript: dict,
    template: str = "caption_burn",
    out_dir: Path | None = None,
    extra: dict | None = None,
) -> Path:
    """
    Inject video path + caption data into a template and write the composition
    directory. Returns the path to the composition directory.

    extra: additional {{KEY}} → value replacements for the template.
    """
    out_dir = out_dir or (video_path.parent / "edit" / "animations" / template)
    out_dir.mkdir(parents=True, exist_ok=True)

    template_file = TEMPLATES_DIR / f"{template}.html"
    if not template_file.exists():
        available = [f.stem for f in TEMPLATES_DIR.glob("*.html")]
        raise FileNotFoundError(
            f"Template '{template}' not found. Available: {available}"
        )

    words = [
        {
            "text": w["text"].strip(".,!?;:\"'()"),
            "start": float(w["start"]),
            "end": float(w["end"]),
        }
        for w in transcript.get("words", [])
        if w.get("type") == "word"
    ]

    captions = _group_captions(words)
    duration = transcript.get("audio_duration") or (words[-1]["end"] if words else 30.0)

    html = template_file.read_text()
    html = html.replace("{{VIDEO_SRC}}", str(video_path.resolve()))
    html = html.replace("{{CAPTIONS_JSON}}", json.dumps(captions))
    html = html.replace("{{DURATION}}", str(round(duration, 3)))
    html = html.replace("{{WIDTH}}", "1920")
    html = html.replace("{{HEIGHT}}", "1080")

    if extra:
        for key, val in extra.items():
            html = html.replace(f"{{{{{key}}}}}", str(val))

    comp_html = out_dir / "composition.html"
    comp_html.write_text(html)
    return out_dir


def render_composition(comp_dir: Path, out_mp4: Path) -> Path:
    """Run `npx hyperframes render` in the composition directory."""
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["npx", "hyperframes", "render", "--out", str(out_mp4.resolve())],
        cwd=str(comp_dir),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"HyperFrames render failed:\n{result.stderr[-2000:]}\n"
            "Make sure Node.js 22+ and ffmpeg are installed:\n"
            "  npm install  (in the project root)\n"
            "  brew install ffmpeg"
        )
    return out_mp4
