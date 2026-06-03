# Video Editing Studio

Full pipeline: raw video → filler removal → motion graphics → final MP4.

## Quick Start

```bash
# 1. Install Python deps
pip install -e .

# 2. Install Node deps (for HyperFrames motion graphics)
npm install

# 3. Set your ElevenLabs API key (transcription)
cp .env.example .env
# → edit .env and add your key from elevenlabs.io/app/settings/api-keys

# 4. Edit a video
python edit.py my_raw_video.mp4
```

Output lands in `<video_folder>/edit/final.mp4`.

## Pipeline

```
Input video
    ↓ ElevenLabs Scribe            word-level transcript + speaker diarization
    ↓ filler_remover.py            detect um/uh/silence → Edit Decision List (EDL JSON)
    ↓ render.py                    FFmpeg: extract segments → concat → loudnorm
    ↓ graphics_builder.py          inject video path + captions into HyperFrames template
    ↓ npx hyperframes render       render motion graphics over video
Output: edit/final.mp4
```

A `timeline.png` waveform visualization is saved to `edit/` after step 2.

## Commands

### Basic — filler removal only
```bash
python edit.py raw.mp4
```

### With auto-captions (2-word chunks, uppercase)
```bash
python edit.py raw.mp4 --overlay caption_burn
```

### With kinetic text overlay
```bash
python edit.py raw.mp4 --overlay kinetic_text
```

### With lower third name card
```bash
python edit.py raw.mp4 --overlay lower_third --name "Jane Smith" --title "Founder & CEO" --show-at 2.0 --show-for 5.0
```

### With full-screen title card intro
```bash
python edit.py raw.mp4 --overlay title_card --eyebrow "Episode 12" --title "The Future of AI" --subtitle "with Jane Smith" --show-at 0 --show-for 4.0
```

### Color grade + no filler removal
```bash
python edit.py raw.mp4 --grade warm_cinematic --no-filler
```

### Fast preview render (720p)
```bash
python edit.py raw.mp4 --preview
```

### Custom output path
```bash
python edit.py raw.mp4 --out exports/episode_01.mp4
```

## All Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--overlay TEMPLATE` | — | Motion graphics template to use |
| `--no-filler` | off | Skip filler word removal |
| `--grade PRESET` | none | Color grade preset |
| `--preview` | off | 720p render (faster, larger CRF) |
| `--speakers N` | 1 | Number of speakers (for diarization) |
| `--out PATH` | edit/final.mp4 | Output file location |
| `--no-timeline` | off | Skip waveform timeline PNG |
| `--name TEXT` | "Your Name" | lower_third: speaker name |
| `--title TEXT` | "Your Title" | lower_third/title_card: title text |
| `--subtitle TEXT` | "" | title_card: subtitle line |
| `--eyebrow TEXT` | "" | title_card: small label above title |
| `--show-at SECS` | 1.0 | lower_third/title_card: when to appear |
| `--show-for SECS` | 4.0 | lower_third/title_card: how long to hold |

## Motion Graphics Templates

All templates live in `graphics/templates/`. They are HTML compositions
rendered by HyperFrames (Puppeteer + FFmpeg) that include the source video.

| Template | Description |
|----------|-------------|
| `caption_burn` | Auto captions from transcript (2-word chunks, uppercase) |
| `lower_third` | Animated name + title in the lower-left corner |
| `title_card` | Full-screen title overlay with dark scrim |
| `kinetic_text` | Words pop in/out kinetically, synced to transcript |

### Customizing Templates

Edit any `graphics/templates/*.html` file directly. Key spots:
- **Font**: Change `font-family` in the `<style>` block
- **Colors**: Edit hex values and gradients
- **Size**: Adjust `font-size` values
- **Position**: Modify `bottom`, `left`, `transform` in CSS

## Color Grade Presets

| Preset | Look |
|--------|------|
| `none` | No grade |
| `warm_cinematic` | Warm shadows, slight desaturated highlights |
| `cool_corporate` | Clean, slightly cool, high contrast |
| `vibrant_social` | Punchy saturation for social media |
| `matte` | Lifted blacks, muted tones |
| `cinema_scope` | 2.39:1 crop + cinematic grade |

## Filler Words Removed

Defined in `pipeline/filler_remover.py` — `FILLER_WORDS`:

```
um  uh  umm  uhh  hmm  mhm
like  basically  literally
you know  i mean  kind of  sort of
```

Edit `FILLER_WORDS` in that file to add or remove entries.

## Silence Threshold

Gaps ≥ **400ms** are cut. Adjust `SILENCE_GAP_MIN` in `pipeline/filler_remover.py`.

## Audio Standard

Output is normalized to **-14 LUFS / -1 dBTP** — the standard for
YouTube, Instagram, and TikTok. Segment boundaries get **30ms audio fades**
to prevent click artifacts.

## Editing the EDL Manually

After step 2, `edit/edl.json` holds the edit decision list. You can:
- Open it and delete ranges you want to cut
- Add ranges to include additional segments
- Then re-run just the render step:
  ```bash
  python -m pipeline.render edit/edl.json -o edit/clean.mp4
  ```

## Requirements

- Python 3.10+
- Node.js 22+
- ffmpeg (`brew install ffmpeg` / `apt install ffmpeg`)
- ElevenLabs API key (free tier works for short videos)
