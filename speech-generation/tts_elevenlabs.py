"""
tts_elevenlabs.py — Drop-in replacement for tts_edge.py using ElevenLabs.

Same CLI shape, same JSON output schema, same {{cue_name}} mechanism — so
the Playwright pipeline keeps consuming meet_dam.timings.json unchanged.

INSTALL

    pip install elevenlabs
    export ELEVENLABS_API_KEY=sk_...

GENERATE

    python tts_elevenlabs.py meet_dam_script.txt \\
        --voice Brian \\
        --out meet_dam

    # Or pass a voice ID directly:
    python tts_elevenlabs.py meet_dam_script.txt \\
        --voice nPczCjzI2devNBz1zQrb \\
        --out meet_dam

Produces meet_dam.mp3 + meet_dam.timings.json (identical schema to Edge).

CUE MARKERS

Same {{cue_name}} syntax. Cues fire at the end of the preceding word's
audio, derived from ElevenLabs' character-level alignment.

VOICES

Run --list-voices for everything available on your account. Recommended
defaults for product narration:

    Brian      warm male, conversational     (default here)
    Will       neutral male, slightly lower
    Adam       crisp male
    Sarah      warm female
    Charlotte  bright female

MODELS

    eleven_multilingual_v2    highest quality, slower         (default)
    eleven_turbo_v2_5         fast, slightly lower fidelity
    eleven_v3                 newest, best prosody (alpha-tier on some accounts)

GOTCHAS

- ElevenLabs returns *character*-level alignment. We re-tokenize using the
  same WORD_RE as the script's cue counter, so word counts always match
  by construction (no mismatch warning needed).
- Speed: --rate '+0%' = normal. ElevenLabs clamps speed to ~[0.7, 1.2];
  '-30%' or '+20%' is the practical envelope.
- Cost: each run is billed against your character quota. The meet_dam
  script is ~1.1k chars, so ~1.1k credits per regeneration.
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path


CUE_RE = re.compile(r"\{\{([a-z0-9_\-]+)\}\}")
WORD_RE = re.compile(r"\w+(?:['‘’]\w+)?")
VOICE_ID_RE = re.compile(r"^[A-Za-z0-9]{20}$")

DEFAULT_VOICE = "Brian"
DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


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
    """Parse Edge-style '+0%', '-10%', '+15%' → speed multiplier (0.7..1.2)."""
    m = re.match(r"^([+-]?)(\d+(?:\.\d+)?)%$", rate.strip())
    if not m:
        raise ValueError(f"Invalid rate: {rate!r} (expected like '+0%', '-10%')")
    sign = -1.0 if m.group(1) == "-" else 1.0
    pct = float(m.group(2))
    return 1.0 + sign * pct / 100.0


def resolve_voice(client, voice: str) -> tuple[str, str]:
    """Accept either a voice ID (20-char alphanumeric) or a voice name."""
    if VOICE_ID_RE.match(voice):
        return voice, voice
    page = client.voices.get_all()
    for v in page.voices:
        if v.name.lower() == voice.lower():
            return v.voice_id, v.name
    available = ", ".join(sorted(v.name for v in page.voices))
    raise ValueError(f"Voice {voice!r} not found on this account. Available: {available}")


def synthesize(
    script: str,
    voice: str,
    rate: str,
    model: str,
    out_base: Path,
) -> dict:
    from elevenlabs import ElevenLabs, VoiceSettings

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY not set. Run: export ELEVENLABS_API_KEY=sk_..."
        )

    audio_path = out_base.with_suffix(".mp3")
    timings_path = out_base.with_name(out_base.name + ".timings.json")

    clean_text, cues = extract_cues(script)
    speed = max(0.7, min(1.2, parse_rate(rate)))

    client = ElevenLabs(api_key=api_key)
    voice_id, voice_name = resolve_voice(client, voice)

    response = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        text=clean_text,
        model_id=model,
        output_format=DEFAULT_OUTPUT_FORMAT,
        voice_settings=VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.0,
            use_speaker_boost=True,
            speed=speed,
        ),
    )

    audio_bytes = base64.b64decode(response.audio_base_64)
    audio_path.write_bytes(audio_bytes)

    chars = list(response.alignment.characters)
    starts = list(response.alignment.character_start_times_seconds)
    ends = list(response.alignment.character_end_times_seconds)

    if not (len(chars) == len(starts) == len(ends)):
        raise RuntimeError(
            f"Alignment arrays have mismatched lengths: "
            f"chars={len(chars)} starts={len(starts)} ends={len(ends)}"
        )

    # Re-tokenize the alignment string with the same WORD_RE used to count
    # cue positions — guarantees word counts match by construction.
    joined = "".join(chars)
    words: list[dict] = []
    for m in WORD_RE.finditer(joined):
        s_idx = m.start()
        e_idx = m.end() - 1
        words.append({
            "text": m.group(),
            "start_ms": int(round(starts[s_idx] * 1000)),
            "end_ms":   int(round(ends[e_idx] * 1000)),
        })

    duration_ms = int(round(ends[-1] * 1000)) if ends else 0

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
        "voice": voice_name,
        "voice_id": voice_id,
        "model": model,
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
    from elevenlabs import ElevenLabs

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY not set. Run: export ELEVENLABS_API_KEY=sk_..."
        )
    client = ElevenLabs(api_key=api_key)
    page = client.voices.get_all()
    for v in sorted(page.voices, key=lambda x: x.name.lower()):
        labels = getattr(v, "labels", None) or {}
        gender = labels.get("gender", "")
        accent = labels.get("accent", "")
        desc = labels.get("description", "") or labels.get("descriptive", "")
        print(f"{v.name:20s}  {v.voice_id:22s}  {gender:8s}  {accent:10s}  {desc}")


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
        default=DEFAULT_VOICE,
        help=f"ElevenLabs voice name or ID (default: {DEFAULT_VOICE})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--rate",
        default="+0%",
        help="Speech rate, e.g. '+0%%', '-10%%', '+15%%'. Clamped to ~[-30%%,+20%%].",
    )
    parser.add_argument(
        "--out",
        default="narration",
        help="Output basename (no extension)",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Print voices available on your account and exit",
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

    result = synthesize(text, args.voice, args.rate, args.model, out_base)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
