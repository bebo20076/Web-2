"""
Analyze a word-level transcript and produce an EDL (Edit Decision List)
that removes filler words and dead silence.

EDL JSON format:
{
  "version": 1,
  "sources": {"stem": "/abs/path/video.mp4"},
  "ranges": [{"source": "stem", "start": 1.2, "end": 4.8, "quote": "..."}],
  "total_duration_s": 87.4,
  "original_duration_s": 120.0,
  "time_saved_s": 32.6
}
"""
import json
import subprocess
from pathlib import Path
from typing import NamedTuple

# Words that are removed when they appear in isolation or before/after silence.
FILLER_WORDS: frozenset[str] = frozenset({
    "um", "uh", "umm", "uhh", "hmm", "mm", "mhm",
    "like", "basically", "literally",
    "you know", "i mean", "kind of", "sort of",
})

SILENCE_GAP_MIN = 0.40   # gaps >= this are candidates for cutting (seconds)
CUT_PAD = 0.05            # padding kept around every cut edge (seconds)
MIN_KEEP = 0.08           # discard any keep segment shorter than this (seconds)


class _Span(NamedTuple):
    start: float
    end: float


def _video_duration(video_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _words(transcript: dict) -> list[dict]:
    return [
        {
            "text": w["text"].lower().strip(".,!?;:\"'()-"),
            "start": float(w["start"]),
            "end": float(w["end"]),
            "speaker": w.get("speaker_id", "S0"),
        }
        for w in transcript.get("words", [])
        if w.get("type") == "word"
    ]


def _cut_spans(words: list[dict], remove_fillers: bool) -> list[_Span]:
    cuts: list[_Span] = []
    if not words:
        return cuts

    # ── silence gaps ─────────────────────────────────────────────────────────
    for i in range(1, len(words)):
        gap_s = words[i - 1]["end"]
        gap_e = words[i]["start"]
        if gap_e - gap_s >= SILENCE_GAP_MIN:
            cuts.append(_Span(gap_s + CUT_PAD, gap_e - CUT_PAD))

    # ── filler words ─────────────────────────────────────────────────────────
    if remove_fillers:
        i = 0
        while i < len(words):
            if words[i]["text"] in FILLER_WORDS:
                start = words[i]["start"] - CUT_PAD
                end = words[i]["end"] + CUT_PAD
                j = i + 1
                while j < len(words) and words[j]["text"] in FILLER_WORDS:
                    end = words[j]["end"] + CUT_PAD
                    j += 1
                cuts.append(_Span(start, end))
                i = j
            else:
                i += 1

    return cuts


def _keep_spans(cuts: list[_Span], duration: float) -> list[_Span]:
    if not cuts:
        return [_Span(0.0, duration)]

    cuts = sorted(cuts, key=lambda s: s.start)
    keep: list[_Span] = []
    cursor = 0.0

    for cut in cuts:
        if cut.start > cursor:
            keep.append(_Span(max(0.0, cursor), min(cut.start, duration)))
        cursor = max(cursor, cut.end)

    if cursor < duration:
        keep.append(_Span(cursor, duration))

    return [s for s in keep if s.end - s.start >= MIN_KEEP]


def build_edl(
    video: Path,
    transcript: dict,
    edit_dir: Path,
    remove_fillers: bool = True,
) -> dict:
    duration = _video_duration(video)
    word_list = _words(transcript)
    cuts = _cut_spans(word_list, remove_fillers)
    keep = _keep_spans(cuts, duration)

    ranges = []
    for span in keep:
        in_range = [
            w for w in word_list
            if w["start"] >= span.start - 0.1 and w["end"] <= span.end + 0.1
        ]
        quote = " ".join(w["text"] for w in in_range[:10])
        ranges.append({
            "source": video.stem,
            "start": round(span.start, 3),
            "end": round(span.end, 3),
            "quote": quote,
        })

    edited = sum(r["end"] - r["start"] for r in ranges)
    return {
        "version": 1,
        "sources": {video.stem: str(video)},
        "ranges": ranges,
        "total_duration_s": round(edited, 3),
        "original_duration_s": round(duration, 3),
        "time_saved_s": round(duration - edited, 3),
    }
