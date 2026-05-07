"""
tts_kokoro.py — Drop-in replacement for tts_edge.py using Kokoro TTS.

Kokoro is an open-source 82M-param TTS model (Apache 2.0). Runs locally on
CPU/MPS/CUDA, no API key, more natural prosody than Edge for narration.

Same CLI shape, same output schema, same {{cue_name}} mechanism as tts_edge.py
— so the Playwright pipeline that consumes meet_dam.timings.json keeps working.

INSTALL

    pip install kokoro soundfile
    brew install espeak-ng ffmpeg     # system deps

GENERATE

    python tts_kokoro.py meet_dam_script.txt \\
        --voice am_michael \\
        --out meet_dam

Produces meet_dam.mp3 and meet_dam.timings.json (identical schema to Edge).

CUE MARKERS

Same {{cue_name}} syntax as tts_edge.py — the cue fires when the word
immediately before it finishes speaking.

VOICES (recommended for product narration)

    am_michael    warm male, conversational      (American)
    am_adam       crisp male, slightly lower     (American)
    af_heart      bright female, default voice   (American)
    af_bella      calm female, even pace         (American)
    bm_george     British male
    bf_emma       British female

Run --list-voices for the full set. Voice prefix encodes language:
    a=American English, b=British English, e=Spanish, f=French,
    h=Hindi, i=Italian, j=Japanese, p=Brazilian Portuguese, z=Mandarin.

GOTCHAS

- First run downloads the model (~330MB) and voice packs (~1MB each).
- Word-token filtering matches tts_edge.py's WORD_RE so cue counts align.
  If you see a "word count mismatch" warning, the script's tokenization
  disagreed with Kokoro's — usually numbers, abbreviations, or "DAM" being
  spelled out. Same fix as Edge: capitalize as "Dam" or restructure.
"""

import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path


CUE_RE = re.compile(r"\{\{([a-z0-9_\-]+)\}\}")
WORD_RE = re.compile(r"\w+(?:['‘’]\w+)?")
WORD_CHAR_RE = re.compile(r"\w", re.UNICODE)
SAMPLE_RATE = 24_000

LANG_BY_PREFIX = {
    "a": "a",  # American English
    "b": "b",  # British English
    "e": "e",  # Spanish
    "f": "f",  # French
    "h": "h",  # Hindi
    "i": "i",  # Italian
    "j": "j",  # Japanese
    "p": "p",  # Brazilian Portuguese
    "z": "z",  # Mandarin
}

KNOWN_VOICES = [
    # American English
    ("af_heart",    "American Female", "default, bright"),
    ("af_bella",    "American Female", "calm, even"),
    ("af_nicole",   "American Female", "soft"),
    ("af_sarah",    "American Female", "warm"),
    ("af_sky",      "American Female", "youthful"),
    ("am_adam",     "American Male",   "crisp, slightly lower"),
    ("am_michael",  "American Male",   "warm, conversational"),
    # British English
    ("bf_emma",     "British Female",  "even"),
    ("bf_isabella", "British Female",  "expressive"),
    ("bm_george",   "British Male",    "rich"),
    ("bm_lewis",    "British Male",    "neutral"),
]


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def extract_cues(script: str) -> tuple[str, list[dict]]:
    """Strip {{cue}} markers and remember which word each follows."""
    cues: list[dict] = []
    parts: list[str] = []
    last = 0
    word_count = 0

    for m in CUE_RE.finditer(script):
        before = script[last:m.start()]
        parts.append(before)
        word_count += count_words(before)
        cues.append({"name": m.group(1), "after_word_index": word_count})
        last = m.end()

    parts.append(script[last:])
    return "".join(parts), cues


def parse_rate(rate: str) -> float:
    """Parse Edge-style '+0%', '-10%', '+15%' → speed multiplier."""
    m = re.match(r"^([+-]?)(\d+(?:\.\d+)?)%$", rate.strip())
    if not m:
        raise ValueError(f"Invalid rate: {rate!r} (expected like '+0%', '-10%')")
    sign = -1.0 if m.group(1) == "-" else 1.0
    pct = float(m.group(2))
    return 1.0 + sign * pct / 100.0


def lang_code_for_voice(voice: str) -> str:
    prefix = voice[:1].lower()
    if prefix not in LANG_BY_PREFIX:
        raise ValueError(
            f"Cannot infer language from voice {voice!r}. Voice should start "
            f"with one of: {sorted(LANG_BY_PREFIX)}"
        )
    return LANG_BY_PREFIX[prefix]


def encode_mp3(wav_bytes: bytes, mp3_path: Path) -> None:
    """Pipe WAV bytes through ffmpeg → MP3."""
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", "pipe:0",
            "-codec:a", "libmp3lame", "-q:a", "2",
            str(mp3_path),
        ],
        input=wav_bytes,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed ({proc.returncode}): {proc.stderr.decode(errors='replace')}"
        )


def synthesize(
    script: str,
    voice: str,
    rate: str,
    out_base: Path,
) -> dict:
    # Heavy imports only when actually synthesizing.
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    audio_path = out_base.with_suffix(".mp3")
    timings_path = out_base.with_name(out_base.name + ".timings.json")

    clean_text, cues = extract_cues(script)
    expected_words = count_words(clean_text)
    speed = parse_rate(rate)
    lang_code = lang_code_for_voice(voice)

    pipeline = KPipeline(lang_code=lang_code)

    audio_chunks: list[np.ndarray] = []
    words: list[dict] = []
    offset_samples = 0

    # Kokoro yields one Result per chunk (sentence-ish). Each Result has
    # .audio (1-D float tensor at 24kHz) and .tokens with per-token timing
    # (start_ts, end_ts in seconds, relative to the start of that chunk).
    for result in pipeline(clean_text, voice=voice, speed=speed):
        audio = result.audio
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        audio = np.asarray(audio, dtype=np.float32)

        offset_ms = int(round(offset_samples * 1000 / SAMPLE_RATE))

        for tok in (result.tokens or []):
            if tok.start_ts is None or tok.end_ts is None:
                continue
            text = (tok.text or "").strip()
            if not text or not WORD_CHAR_RE.search(text):
                continue
            words.append({
                "text": text,
                "start_ms": offset_ms + int(round(tok.start_ts * 1000)),
                "end_ms":   offset_ms + int(round(tok.end_ts   * 1000)),
            })

        audio_chunks.append(audio)
        offset_samples += len(audio)

    if not audio_chunks:
        raise RuntimeError("Kokoro produced no audio — empty script?")

    full_audio = np.concatenate(audio_chunks)
    duration_ms = int(round(len(full_audio) * 1000 / SAMPLE_RATE))

    # WAV → ffmpeg → MP3 (matches tts_edge.py output format).
    wav_buf = io.BytesIO()
    sf.write(wav_buf, full_audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    encode_mp3(wav_buf.getvalue(), audio_path)

    if expected_words != len(words):
        print(
            f"WARNING: word count mismatch — script tokenized to {expected_words}, "
            f"Kokoro returned {len(words)} word tokens. Cue timings may be off "
            f"by a few words; check for numbers, abbreviations, or unusual "
            f"punctuation in the script.",
            file=sys.stderr,
        )

    cue_timings: list[dict] = []
    for c in cues:
        idx = c["after_word_index"]
        if idx <= 0:
            at_ms = 0
        elif idx <= len(words):
            at_ms = words[idx - 1]["end_ms"]
        else:
            at_ms = words[-1]["end_ms"] if words else 0
        cue_timings.append({"name": c["name"], "at_ms": at_ms})

    timings = {
        "voice": voice,
        "rate": rate,
        "duration_ms": duration_ms,
        "text": clean_text,
        "words": words,
        "cues": cue_timings,
    }
    timings_path.write_text(json.dumps(timings, indent=2, ensure_ascii=False))

    return {
        "audio": str(audio_path),
        "timings": str(timings_path),
        "words": len(words),
        "cues": len(cue_timings),
        "duration_ms": duration_ms,
    }


def list_voices() -> None:
    for name, locale, note in KNOWN_VOICES:
        print(f"{name:12s}  {locale:18s}  {note}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "script",
        nargs="?",
        help="Path to script .txt file (or '-' for stdin)",
    )
    parser.add_argument(
        "--voice",
        default="am_michael",
        help="Kokoro voice id (see --list-voices)",
    )
    parser.add_argument(
        "--rate",
        default="+0%",
        help="Speech rate, e.g. '+0%%', '-10%%', '+15%%'",
    )
    parser.add_argument(
        "--out",
        default="narration",
        help="Output basename (no extension)",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Print available voices and exit",
    )
    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        return 0

    if not args.script:
        parser.error("script path required (or use --list-voices)")

    text = (
        sys.stdin.read()
        if args.script == "-"
        else Path(args.script).read_text(encoding="utf-8")
    )
    text = text.strip()
    if not text:
        parser.error("empty script")

    out_base = Path(args.out)
    if out_base.parent and str(out_base.parent) not in (".", ""):
        out_base.parent.mkdir(parents=True, exist_ok=True)

    result = synthesize(text, args.voice, args.rate, out_base)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
