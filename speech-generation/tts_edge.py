"""
tts_edge.py — Generate narration audio + word timings + action cues using
Microsoft Edge TTS.

Free, no API key, neural voices, word-level boundaries — ideal for syncing
a Playwright capture pipeline to a spoken script.

INSTALL

    pip install edge-tts

GENERATE

    python tts_edge.py meet_dam_script.txt \\
        --voice en-US-AndrewMultilingualNeural \\
        --out meet_dam

Produces:
    meet_dam.mp3              the audio
    meet_dam.timings.json     word timings + cue timestamps

CUE MARKERS

Insert {{cue_name}} anywhere in the script to anchor an action timestamp
to that point. The cue fires when the word immediately before it finishes
speaking. Cue names: lowercase letters, digits, underscore, hyphen.

    First, the provider. {{click_providers}} Paste your key,
    {{paste_key}} hit Test, {{click_test}} green check. {{show_green}}

OUTPUT SCHEMA (meet_dam.timings.json):

    {
      "voice": "en-US-AndrewMultilingualNeural",
      "rate": "+0%",
      "duration_ms": 89500,
      "text": "Meet DAM. Background agents...",
      "words": [
        { "text": "Meet", "start_ms": 0,   "end_ms": 320 },
        ...
      ],
      "cues": [
        { "name": "open_dam",        "at_ms":  4200 },
        { "name": "click_providers", "at_ms":  8950 },
        ...
      ]
    }

CONSUME FROM PLAYWRIGHT (TypeScript):

    const t = JSON.parse(fs.readFileSync("meet_dam.timings.json", "utf8"));
    const at = Object.fromEntries(t.cues.map(c => [c.name, c.at_ms]));
    // schedule: at at.click_providers, fire the click

LIST VOICES

    python tts_edge.py --list-voices | grep "en-US.*Multilingual"

Recommended voices for product narration:
    en-US-AndrewMultilingualNeural    warm male, conversational
    en-US-BrianMultilingualNeural     crisp male, slightly formal
    en-US-AvaMultilingualNeural       bright female, energetic
    en-US-EmmaMultilingualNeural      calm female, even pace

GOTCHAS

- Numbers like "127.0.0.1" expand to many spoken words and may misalign
  cue counts. Spell them out or restructure the line.
- ALL-CAPS acronyms ("HTML", "MCP", "API") are usually read letter-by-letter
  but each emits one word boundary, so counts still match. If a name like
  "DAM" gets spelled out instead of spoken as a word, capitalize it as
  "Dam" or use SSML.
- The script logs a warning if its tokenization disagrees with TTS — use
  that to spot the problem word.
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import edge_tts


CUE_RE = re.compile(r"\{\{([a-z0-9_\-]+)\}\}")
WORD_RE = re.compile(r"\w+(?:['‘’]\w+)?")


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def extract_cues(script: str) -> tuple[str, list[dict]]:
    """Strip {{cue}} markers and remember which word each follows.

    Returns (clean_text, [{"name": str, "after_word_index": int}, ...]).
    A cue with after_word_index = 0 fires at t = 0 (before any word).
    """
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


async def synthesize(
    script: str,
    voice: str,
    rate: str,
    out_base: Path,
) -> dict:
    audio_path = out_base.with_suffix(".mp3")
    timings_path = out_base.with_name(out_base.name + ".timings.json")

    clean_text, cues = extract_cues(script)
    expected_words = count_words(clean_text)

    communicate = edge_tts.Communicate(clean_text, voice, rate=rate)

    words: list[dict] = []
    duration_ms = 0

    with audio_path.open("wb") as af:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                af.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # Edge TTS reports offsets in 100-ns ticks (Windows FILETIME).
                start_ms = chunk["offset"] // 10_000
                dur_ms = chunk["duration"] // 10_000
                end_ms = start_ms + dur_ms
                words.append(
                    {
                        "text": chunk["text"],
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                    }
                )
                duration_ms = max(duration_ms, end_ms)

    if expected_words != len(words):
        print(
            f"WARNING: word count mismatch — script tokenized to {expected_words}, "
            f"TTS returned {len(words)} word boundaries. Cue timings may be off "
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


async def list_voices() -> None:
    voices = await edge_tts.list_voices()
    for v in voices:
        print(
            f"{v['ShortName']:42s}  {v['Gender']:7s}  {v['Locale']:10s}  "
            f"{v.get('FriendlyName', '')}"
        )


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
        default="en-US-AndrewMultilingualNeural",
        help="Edge TTS voice id (see --list-voices)",
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
        help="Print all available voices and exit",
    )
    args = parser.parse_args()

    if args.list_voices:
        asyncio.run(list_voices())
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

    result = asyncio.run(synthesize(text, args.voice, args.rate, out_base))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
