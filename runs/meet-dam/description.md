# Meet DAM — 90-second walkthrough (first production run)

The reference scene from `RECORDER.md`. End-to-end tour of DAM's
golden path: empty state → provider configured → first agent created
→ first prompt run → files produced.

## App

DAM running locally at `http://dam.localhost:4444/` (k3s via lima,
deployed with `mise run cluster:install` from `~/Dev/ibm/dam`).
Login goes through Keycloak. Dev credentials: `dev` / `dev`.

(Earlier prior run `dam-add-provider` used `humr.localhost:4444` —
DAM has since been renamed/repointed at `dam.localhost`. Confirm with
the user which host the local cluster is currently exposing.)

## Audience

Developers evaluating DAM for the first time. They've never seen the
UI. By the end of the video they should know:

1. DAM provisions per-agent Kubernetes pods (credentials safe,
   sandboxed, scheduled).
2. Onboarding is three steps, gated by a get-started bar.
3. An agent run produces real files in a sandboxed workspace, visible
   inline in the UI.
4. The same right panel surfaces MCPs, skills, and schedules.

## Demo path

Login → Agents (empty) → click "Set up a provider" → Providers page →
API Key tab → paste key → Test → Save → back to Agents (pill 1
green) → click "Set up connections" → Connections page → pan → back
to Agents → click Add Agent → template picker → name → Create →
pulsing Starting → Running → click row → chat opens → type prompt →
send → streaming response → Done → Files tab → click app.js → flash
to index.html → back to MCPs / Skills / Schedules tabs → outro.

## Recording prerequisites

- Local DAM cluster running and reachable at `dam.localhost:4444`.
- Logged out before pressing record (so the take starts at the
  Keycloak login). Or: skip login via storage-state injection (TBD).
- **Empty starting state** — zero agents, zero providers configured —
  so the get-started bar renders. Easiest reset:
  `mise run cluster:uninstall && mise run cluster:install` from the
  DAM repo. Confirm with user whether to do this fresh or reuse.
- Anthropic API key available to paste during the Provider beat.
  Either real (and redacted in post) or a fake `sk-ant-…` string and
  cut/replace the response banner if Test fails.
- Theme: light (per prior `dam-add-provider/init.json`). Carry over
  the same `init.json` to this run.

## Open questions for the user

- **DAM host**: still `dam.localhost:4444` per RECORDER.md, or now
  on a different host?
- **Real vs fake API key**: do we have a real key we can paste and
  redact in post, or do we cheat the success state?
- **Chat determinism**: the agent's response timing (streaming
  thoughts, file writes) is non-deterministic. Plan: drive it
  hand-paced and accept a real take; re-record if pacing is off.
- **Scene scope check**: 1:30 budget assumes brisk delivery. Drop
  the Connections beat or shorten Files-panel if we run long.

## Out of scope for this run

- Multi-aspect-ratio output. Single 1920×1080.
- Cinematic intro/outro. Use a placeholder title card; final polish
  in Resolve.
- Localization. English narration only.
