# speech-generation

Narration TTS for the recorder pipeline. Multiple backends; the canonical
one is `tts.ts` (ElevenLabs, invoked via `pnpm tts`). The Python alternates
exist because they each have a property the canonical one lacks — pick
based on what the run needs.

## Choosing a backend

| Backend                | API key   | Cue timings | Notes                                          |
|------------------------|-----------|-------------|------------------------------------------------|
| `tts.ts` (canonical)   | ElevenLabs | no          | `pnpm tts …`. Strips `{{cues}}` before synth. |
| `tts_elevenlabs.py`    | ElevenLabs | yes         | Same voices as `tts.ts`, plus per-cue at_ms.   |
| `tts_edge.py`          | none      | yes         | Free, neural Edge voices.                      |
| `tts_kokoro.py`        | none      | yes         | Local model (Apache 2.0). Heavier deps.        |
| `tts_aligned.py`       | ElevenLabs | yes (forced) | Pads silence so cue at_ms equals click times — only useful for fully-scripted recordings, not the hand-driven flow. |

Cue timings are NOT required for the manual-recording workflow — the
`produce-feature-video` skill matches cues to clicks by their order in
the script, so the canonical `pnpm tts` is enough. Reach for the cue-aware
backends only if you want the audio to lock to pre-recorded click times.

## Canonical usage

```sh
ELEVENLABS_API_KEY=sk_… pnpm tts --run <slug>
# reads runs/<slug>/script.md, writes runs/<slug>/speech.mp3
```

For premium ElevenLabs voices (not on the free tier), generate the audio
in the ElevenLabs UI and drop the file at `runs/<slug>/speech.mp3` by
hand — the API doesn't expose those voices.

## Cue convention

Inside a script, mark every visible UI moment with `{{cue-name}}`. Use the
target element's `aria-label` or `id` as the cue name when one exists, so
the recording binder can verify each cue lands on the right click.

```
First, open the {{providers-tab}}. Paste your key into {{api-key-input}}
and click {{test-button}}.
```
