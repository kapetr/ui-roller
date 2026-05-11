# Zoom intent — Meet DAM

Camera approach: wide for navigation and big-picture beats; tighter
during clicks so the viewer follows the action without losing
context. Zoom factor stays in the 1.3–1.5 safe band.

## Wide

- **Hook + outro.** Opening claim ("Dam runs your AI coding agent…")
  and closing line ("That's Dam") are establishing — let the page
  breathe.
- **Page transitions.** Post-login load, Providers → Agents,
  Agents → Connections, Connections → Agents, modal open, modal
  close, route to chat. Always wide while the layout swaps.
- **Connections panorama.** Narration enumerates "OAuth apps, MCP
  servers, custom secrets" — stay wide so all three sections sit on
  screen together. (A slow downward pan is a Resolve-time tweak if
  it reads static.)
- **Pod provisioning.** "Underneath, Dam is spinning up a fresh
  pod…" — viewer sees the agent row in the agents list while the
  badge transitions Starting → Running.
- **Streaming response.** "The agent runs inside the pod…" — chat
  streams; viewer follows the streaming, not a detail.

## Zoom-in

1. **Login form** (cues `username`, `kc-login`).
   Region: the Keycloak sign-in card, centred.
   Zoom: 1.4×.
   Why: small card on a mostly-empty page; tightening hides the dead
   space and gives the typing weight.

2. **Get-started pill 1** (cue `set-up-a-provider`).
   Region: the top get-started bar, centred on pill 1.
   Zoom: 1.5×.
   Why: pills are small, the empty agents list isn't doing anything;
   the tighten gives the click presence.

3. **Anthropic provider card** (cues `token-input`, `test`, `save`).
   Region: the Anthropic card — OAuth input row plus Test and Save.
   Zoom: 1.4×.
   Why: the whole beat happens in one row; the rest of the page is
   decoration. Holds across all three clicks.

4. **Add-agent modal — template list** (cue `claude-code`).
   Region: the template-picker section inside the modal.
   Zoom: 1.3×.
   Why: modal sits on a dimmed background already; a slight tighten
   focuses on the templates without going claustrophobic.

5. **Add-agent modal — configure form** (cue `create-agent`).
   Region: the Name + Connections + Network-access form.
   Zoom: 1.3×.
   Why: shows the per-agent scoping the narration is selling, all in
   one frame, ending on Create.

6. **Chat input** (cues `prompt-input`, `send`).
   Region: the bottom chat-input area + Send button.
   Zoom: 1.4×.
   Why: typing is the action; the rest of the chat panel is empty
   until the response streams.

7. **File viewer** (cue `app-js`).
   Region: the right panel — files tree plus file contents after the
   click.
   Zoom: 1.3×.
   Why: the right panel is narrow already (~340 CSS px); a small
   tighten lets the code be readable without isolating it from the
   panel structure.

8. **Right-panel tabs walk** (cues `log`, `config`).
   Region: same as item 7, held while the user tab-walks.
   Zoom: 1.3× (continuation of #7).
   Why: keeps continuity; the viewer sees the tabs change in place
   without a camera move.

## Considered, deliberately wide

- **Connections page section-by-section zoom**: cursor isn't there
  and the camera would have to teleport between sections. Wide is
  calmer.
- **Agent badge "Starting → Running"**: a tight zoom on the badge
  reads as drama, but losing the surrounding row strips context.
