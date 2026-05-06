// Meet DAM — full-length scripted walkthrough.
//
// Cues come from speech-generation/meet_dam.timings.json. Each action
// that should fire on a narration beat gets a `cue:` matching the
// script's `{{cue}}` markers. The recorder waits until the cue's at_ms
// before firing the action, then logs actual drift to actual.timings.json.
//
// Status: SCAFFOLD. Selectors are guesses based on the humr probe; verify
// each beat in the live UI and tighten the selector + timing as you go.
// Beats marked TODO are awaiting selector confirmation or a UI feature
// that may not exist yet in dev mode.
//
// The chat segment (send_prompt → show_files → click_file → scroll_files)
// will likely need either:
//   (a) a canned/dev-mode chat response in DAM so timing is deterministic,
//   (b) the hand-driven fallback recorder mode (TODO step 5 in POC_PLAN).

import type { Actions } from "../actions/instrumented.ts";
import { config } from "../shared/config.ts";

export const meta = {
  timingsPath: "speech-generation/meet_dam.timings.json",
};

export async function run(actions: Actions): Promise<void> {
  // ── Pre-roll: login. Not part of the narration timeline; the audio
  // assembler should align narration start with the post-login frame.
  // Storage-state injection would let us skip login entirely — TODO.
  await actions.navigate(config.baseUrl);
  await actions.type("#username", "dev", "username");
  await actions.type("#password", "dev", "password");
  await actions.click("#kc-login", "sign-in");
  await actions.waitFor({
    visible: 'button:has-text("Set up a provider")',
    reason: "wait-for-dam-loaded",
  });

  // ── Beat: opening shot (open_dam at audio t=0)
  // Narration is establishing — just hold the agents list.
  await actions.wait(800, "settle-after-login");

  // ── Beat: "Three steps to your first agent. {{step1_highlight}}"
  // TODO: hover the get-started bar to draw attention. For now, no-op
  // (cue floor still applies — recorder waits to step1_highlight at_ms).
  // Could be: await actions.hover('text=GET STARTED', { cue: "step1_highlight" });

  // ── Beat: "First, the provider. {{click_providers}}"
  await actions.click('button:has-text("Set up a provider")', {
    cue: "click_providers",
    label: "open-providers",
  });

  // ── Beat: "Paste a key or an OAuth token. {{paste_key}}"
  // TODO: confirm the input selector. From the humr probe, Anthropic
  // section has an input with placeholder "sk-ant-oat-…".
  await actions.type(
    'input[placeholder^="sk-ant-"]',
    "sk-ant-fake-token-for-demo-recording",
    { cue: "paste_key", label: "paste-key" },
  );

  // ── Beat: "Hit Test, {{click_test}}"
  await actions.click('button:has-text("Test")', {
    cue: "click_test",
    label: "test-credential",
  });

  // ── Beat: "green check, you're good. {{show_green}}"
  // Wait for the validation result before proceeding.
  await actions.waitFor({
    text: "valid",
    in: '[role="status"], .toast, .notification',
    timeoutMs: 5000,
    reason: "wait-for-credential-valid",
  });

  // ── Beat: "Save. {{click_save}}"
  await actions.click('button:has-text("Save")', {
    cue: "click_save",
    label: "save-provider",
  });

  // ── Beat: "Connections next. {{click_connections}}"
  await actions.click('button:has-text("Set up connections")', {
    cue: "click_connections",
    label: "open-connections",
  });

  // ── Beat: "GitHub, Slack, Linear, custom MCPs… {{show_connectors}}"
  // TODO: pan slowly over the connector options. Without zoom/pan in
  // ffmpeg, just dwell. Resolve will add the pan in post around this
  // marker.
  await actions.wait(1500, "show-connectors");
  // TODO: cue would attach here if we drove a hover or scroll.

  // ── Beat: "We'll skip for this run. {{back_to_list}}"
  await actions.click('a:has-text("Agents"), button:has-text("Agents")', {
    cue: "back_to_list",
    label: "back-to-agents",
  });

  // ── Beat: "Now the agent. {{click_add_agent}}"
  await actions.click('button:has-text("Add Agent")', {
    cue: "click_add_agent",
    label: "open-add-agent",
  });

  // ── Beat: "Pick the Claude Code harness. {{pick_template}}"
  // TODO: confirm template picker layout.
  await actions.click('text="Claude Code"', {
    cue: "pick_template",
    label: "pick-claude-template",
  });

  // ── Beat: "Give it a name, {{type_name}}"
  // TODO: confirm name field selector.
  await actions.type(
    'input[name="name"], input[placeholder*="name" i]',
    "Todo App Builder",
    { cue: "type_name", label: "agent-name" },
  );

  // ── Beat: "describe what its job is, {{type_description}}"
  await actions.type(
    'textarea[name="description"], textarea[placeholder*="describe" i]',
    "Builds tiny demo apps to spec",
    { cue: "type_description", label: "agent-description" },
  );

  // ── Beat: "pick which connections it can see, {{select_connections}}"
  // TODO: depends on connections-picker UI.
  // await actions.click('...', { cue: "select_connections" });

  // ── Beat: "choose its network access, {{select_network}}"
  // TODO: depends on network-access UI.
  // await actions.click('...', { cue: "select_network" });

  // ── Beat: "and Create. {{click_create}}"
  await actions.click('button:has-text("Create")', {
    cue: "click_create",
    label: "create-agent",
  });

  // ── Beat: "The pod spins up. The badge says Starting — {{show_starting}}"
  // Hold while the pod-status badge transitions. Use waitFor to dwell
  // on the Starting state long enough to be visible.
  await actions.waitFor({
    text: "Starting",
    timeoutMs: 10_000,
    reason: "wait-for-pod-starting",
  });
  await actions.wait(1000, "show-starting");

  // ── Beat: "a few seconds, then Running. {{show_running}}"
  await actions.waitFor({
    text: "Running",
    timeoutMs: 60_000,
    reason: "wait-for-pod-running",
  });

  // ── Beat: "Click in. {{click_chat}}"
  // TODO: depends on agent row selector.
  await actions.click('[data-testid="agent-row"]', {
    cue: "click_chat",
    label: "open-chat",
  });

  // ─────────────────────────────────────────────────────────────────
  // Chat segment — see scene-status comment at top of file. Either
  // depends on canned dev-mode response or hand-driven fallback. The
  // cues are wired here so once the response is deterministic the
  // scene runs end-to-end.
  // ─────────────────────────────────────────────────────────────────

  // ── Beat: "Time for a real test. … {{send_prompt}}"
  // TODO: confirm chat input + send button selectors.
  await actions.type(
    'textarea[placeholder*="message" i], textarea[name="prompt"]',
    "Build me a tiny TODO app as three files — index.html, styles.css, app.js. " +
      "Tasks should persist in localStorage with a satisfying check animation. " +
      "Keep each file under 50 lines.",
    { cue: "send_prompt", label: "compose-prompt" },
  );
  await actions.click('button[type="submit"], button:has-text("Send")', {
    label: "send-prompt-submit",
  });

  // ── Beat: "Files appear in the right panel as they land. {{show_files}}"
  await actions.waitFor({
    text: "Done",
    timeoutMs: 120_000,
    reason: "wait-for-agent-finish",
  });
  // Cue floor only — narration's at_ms governs when this beat is
  // visible. If the agent is still streaming, drift is recorded for
  // the assembler.

  // ── Beat: "Open one — {{click_file}} clean markup."
  await actions.click('text="app.js"', {
    cue: "click_file",
    label: "open-app-js",
  });

  // ── Beat: "Styles. App. No trash. {{scroll_files}}"
  // TODO: iterate over the three files with brief dwells.
  await actions.wait(1500, "scroll-files-placeholder");

  // ── Beat: outro
  await actions.wait(2000, "outro-hold");
}
