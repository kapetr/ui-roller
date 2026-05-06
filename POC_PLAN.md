# POC Plan — speech + click effects + Resolve zoom

## Goal

End-to-end product video produced by:

1. Hand-driven Playwright capture (you click; the recorder logs every
   move + click).
2. Composited cursor + click ring/ripple over the raw screencast.
3. TTS narration generated at natural pace from a plain script.
4. Zoom/pan + audio mux + cuts + intro/outro in DaVinci Resolve.

ffmpeg owns the deterministic layer compositing (cursor, click effects).
Resolve owns cinematic transforms, audio mux, cuts, polish.

The primary path is **natural-pace audio + human pacing the recording
to it**. No automatic audio alignment is needed — the human watching
the script play matches actions to phrases, and any mismatch is fixed
by a simple Resolve trim.

## Primary workflow

| Step | Command |
|---|---|
| 1. Write narration script | Plain text in `speech-generation/<name>_script.txt`. No `{{cue}}` markers needed. |
| 2. Generate audio | `ELEVENLABS_API_KEY=sk_… pnpm tts speech-generation/<name>_script.txt` |
| 3. Manual record | Play the audio on headphones (any player). In another shell: `pnpm record-manual <url>`. Click through to match the narration. Close the browser when done. |
| 4. Cursor + click effects | `pnpm assemble <label>` → produces `out/{cursor.mov, click.mov, final.mp4}`. |
| 5. Resolve assembly | `python3 resolve/to-resolve.py <label> --audio speech-generation/<name>.mp3` (when Resolve Studio is available). Imports raw/cursor/click + audio onto V1/V2/V3 + A1, drops a marker per click. You add zooms around markers, trim mismatches, intro/outro, render. |

## Pipeline (artifacts)

```
recorder        →  raw.mov
                   events.json

compositor      →  cursor.mov            (transparent ProRes 4444)
                   click.mov             (transparent ProRes 4444)
                   final.mp4             (raw + cursor + click composited)

TTS (Node)      →  narration.mp3         (natural pace, no timing constraints)

resolve/to-resolve.py
                →  Resolve project file
                   - V1 raw, V2 cursor, V3 click overlays
                   - A1 narration
                   - Marker per click event (named with label/cue)
                   → hand off for zoom keyframes, trim, intro/outro, render
```

## Secondary workflows (not used by default)

### Scripted scene with cue alignment
For automated re-renders where human pacing isn't an option (e.g., CI
recordings, multi-language re-renders). The bones for this are already
shipped:

- `actions.click(target, { cue })` — recorder waits until `cue.at_ms`
  before firing.
- `actual.timings.json` — drift report per cue.
- `speech-generation/tts_aligned.py` — generates per-segment audio with
  silence padding so cue at_ms matches click t exactly. **Experimental**
  (silence padding can sound unnatural; speed shifts wobble prosody).
  Don't use for the primary flow.

### Meet DAM scene scaffold
`src/scenes/meet-dam.ts` walks the script's beats with `cue:` per
action. Currently TODO-blocked on selector verification against the
live DAM cluster. Useful when scripted-scene workflow becomes
necessary; orthogonal to the primary hand-driven flow.

## Progress

- [x] v0 scaffold (capture pipeline, ProRes intermediate)
- [x] Cursor compositor (sprite, eased path, curved bezier)
- [x] HD layout @ 2× DPR capture (`--force-device-scale-factor=2`)
- [x] Cursor / page-mouse sync via delay-then-teleport
- [x] Logger / video clock alignment (`Screencast.firstFrame` → `Logger.alignTo`)
- [x] Click-effect compositor (expanding ring, antialiased, alpha-blended)
- [x] Click-effect timing tied to page-response paint (`effectT`)
- [x] Hand-driven recorder (`pnpm record-manual <url>` — page-side mousemove + click hooks, browser-close stops)
- [x] TTS Node script (`pnpm tts <script.txt>` — ElevenLabs, natural pace, strips cue markers)
- [x] Resolve export skeleton (probe.py + to-resolve.py — import V1/V2/V3 + A1, click markers)
- [x] Speech cue plumbing (`actions.click(target, { cue })`, `actual.timings.json`) — for scripted-scene secondary path
- [x] Semantic `waitFor({ visible | text | networkIdle | predicate })` — for scripted-scene secondary path
- [x] Audio aligner (`speech-generation/tts_aligned.py`) — experimental, secondary path only
- [x] Meet DAM scene scaffold — TODO-blocked on live cluster selector verification
- [ ] **Resolve Studio** — pending license; primary blocker for end-to-end test
- [ ] Resolve transform keyframes via API (deferred — user adds zoom by hand around markers; clean automation requires Fusion comps and isn't worth it for v0)

## Open questions

- Resolve target version: confirm Python scripting API matches the
  installed Resolve once Studio is available.
- For longer videos with chat-heavy beats: split narration into
  segments around the unpredictable beats so the audio file boundaries
  give natural cut points in Resolve.
