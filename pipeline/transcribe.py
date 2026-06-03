"""
Transcribe a video using ElevenLabs Scribe (word-level timestamps).

Usage:
  python -m pipeline.transcribe <video>
  python -m pipeline.transcribe <video> --num-speakers 2 --language en

Output: edit/transcripts/<stem>.json
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests


def load_api_key() -> str:
    key = os.getenv("ELEVENLABS_API_KEY")
    if key:
        return key
    for search in [Path.cwd(), *Path.cwd().parents]:
        env_file = search / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("ELEVENLABS_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit(
        "ELEVENLABS_API_KEY not found.\n"
        "Create .env with: ELEVENLABS_API_KEY=your_key_here\n"
        "Get a key at: https://elevenlabs.io/app/settings/api-keys"
    )


def extract_audio(video_path: Path, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    wav = cache_dir / f"{video_path.stem}_16k.wav"
    if wav.exists():
        return wav
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
            str(wav),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"ffmpeg audio extraction failed:\n{result.stderr}")
    return wav


def call_scribe(
    wav_path: Path,
    api_key: str,
    num_speakers: int = 1,
    language: str = "en",
) -> dict:
    with open(wav_path, "rb") as f:
        resp = requests.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": api_key},
            files={"audio": (wav_path.name, f, "audio/wav")},
            data={
                "model_id": "scribe_v1",
                "language_code": language,
                "diarize": "true",
                "num_speakers": str(num_speakers),
                "timestamps_granularity": "word",
                "tag_audio_events": "true",
            },
            timeout=300,
        )
    resp.raise_for_status()
    return resp.json()


def transcribe_one(
    video_path: Path,
    edit_dir: Path,
    num_speakers: int = 1,
    language: str = "en",
) -> dict:
    transcript_dir = edit_dir / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    cache = transcript_dir / f"{video_path.stem}.json"

    if cache.exists():
        print(f"       Cached transcript: {cache.name}")
        return json.loads(cache.read_text())

    api_key = load_api_key()
    print(f"       Extracting audio from {video_path.name}...")
    wav = extract_audio(video_path, edit_dir / "_audio")

    print("       Sending to ElevenLabs Scribe (word-level)...")
    data = call_scribe(wav, api_key, num_speakers=num_speakers, language=language)

    cache.write_text(json.dumps(data, indent=2))
    word_count = sum(1 for w in data.get("words", []) if w.get("type") == "word")
    duration = data.get("audio_duration", 0)
    print(f"       {word_count} words | {duration:.1f}s | saved → {cache.name}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe video with ElevenLabs Scribe")
    parser.add_argument("video")
    parser.add_argument("--edit-dir")
    parser.add_argument("--num-speakers", type=int, default=1)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    video = Path(args.video).resolve()
    edit_dir = Path(args.edit_dir) if args.edit_dir else video.parent / "edit"
    transcribe_one(video, edit_dir, num_speakers=args.num_speakers, language=args.language)


if __name__ == "__main__":
    main()
