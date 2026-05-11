# Meet DAM — exploration

App: DAM. Local URL: `http://humr.localhost:4444/` (config still uses
the old `humr` host; RECORDER.md's `dam.localhost` reference is stale).
Login goes through Keycloak. Dev credentials: `dev` / `dev`.

## Recording state requirements

- Logged out before pressing record (so the take starts at Keycloak).
- **Empty cluster state** — zero providers, zero agents — so the
  get-started bar with three numbered pills renders. Reset:
  `mise run cluster:uninstall && mise run cluster:install` from the
  DAM repo.
- Light theme. `init.json` sets `humr-theme=light` on the
  `humr.localhost:4444` origin (carry over from `dam-add-provider`).
- An OAuth token from `claude setup-token` (recorded locally) ready
  to paste — or a fake string and we cut/replace the Test result
  in post.

## Path the script walks

| Beat | Cue(s) | Click target |
|---|---|---|
| Login | `username`, `kc-login` | Keycloak username field, Sign In button |
| Get-started pill 1 | `set-up-a-provider` | Top bar "Set up a provider" pill |
| Provider OAuth (default tab) | `token-input` | OAuth token field |
| Provider Test | `test` | Test button |
| Provider Save | `save` | Save button (auto-jumps back to agents list) |
| Get-started pill 2 | `set-up-connections` | Top bar "Set up connections" pill |
| Back to Agents | `agents` | Sidebar Agents button (or back link) |
| Add Agent | `add-agent` | "Add Agent" button on Agents page |
| Pick template | `claude-code` | "claude-code" template card in modal |
| Create | `create-agent` | "Create Agent" button after name + toggles |
| Click into agent | `agent-row` | Newly-created agent row |
| Type prompt | `prompt-input` | Chat textbox "Message agent..." |
| Send | `send` | Send button (right of textbox) |
| Open app.js | `app-js` | `app.js` entry in right-panel files tree |
| Switch to index.html | `index-html` | `index.html` entry |
| Log tab | `log` | Right-panel "log" tab (tabs are: files, log, config) |
| Config tab | `config` | Right-panel "config" tab |

Stray clicks that may happen during the take and should be ignored
by the binder:

- Password field click between username and sign-in.
- Connection / Network-access toggles in the Add Agent modal — the
  script narration covers them but no cue is reserved; user toggles
  whatever feels right.

## UI surprises worth flagging

- **Right-panel tabs are `files / log / config`**, not the
  `MCPs / skills / schedules` mentioned in RECORDER.md. Script has
  been updated to match.
- The Files tab is the right panel's default-active tab on chat
  entry, so there's no `{{files}}` click cue — the user enters chat
  and the workspace is already visible.
- Add Agent modal's Configure step has both a Connections checkbox
  group (provider checkboxes — Anthropic API Key, etc.) and a
  Network access radio group (Trusted defaults / Strict / Allow
  everything). The script's "connections and capabilities" line
  covers both.
- OAuth Token tab is the default-active tab on the Provider page.
  No tab-switch click needed.
- Templates available: `claude-code`, `code-guardian`,
  `google-workspace`, `pi-agent`. Script lists "Claude Code, pi.dev,
  or your own" — pi.dev is informal for pi-agent; close enough for
  narration.

## Things deferred to post-recording

- Concrete bboxes for any zoom region that isn't anchored on a click
  (e.g. wide-pan over the get-started bar, focus on the provider
  card, focus on the right-panel tabs). These come from
  frame-extracted screenshots in step 10.
- Confirming the agent's chat actually streams + writes files in a
  reasonable time. The take itself is the test — re-record if it
  drags.
