# DAM exploration — add Anthropic provider

App: DAM. Local URL: http://humr.localhost:4444/. Login goes through
Keycloak at http://keycloak.localhost:4444. Dev credentials: `dev` / `dev`.

## Recording precondition

For the demo to begin at the login screen, the recording machine must
be logged out before pressing record. If a session cookie persists,
clear it via the browser's site-data tools — or just open the URL once,
log out, and close the browser before launching `pnpm record-manual`.

The recorder picks up `init.json` in this folder, which sets
`humr-theme=light` in localStorage on the `humr.localhost:4444`
origin before the page loads. Don't re-apply manually.

## Routes / states the demo touches

| Step                  | URL                              | What's shown                                                        |
|---|---|---|
| Login                 | `keycloak.localhost:4444/realms/humr/...` | Keycloak sign-in form                                       |
| Home (post-login)     | `/`  (renders the Agents page)   | Sidebar + top get-started bar + "No agents yet" body                |
| Providers             | `/providers`                     | Anthropic card with OAuth Token / API Key tabs + Coming Soon below  |

## Key elements

Note: most buttons have **no `aria-label` and no `id`**. The recorder's
`label` field falls back to the button's `innerText` (trimmed, first 40
chars). Cue names below match what'll show in `events.json`'s `label`
field for token-based binding-verification.

### Login (Keycloak)

| Cue                | Element                  | Selector       | Bbox notes                                |
|---|---|---|---|
| `username`         | Username input           | `#username`    | Top-centre of the login card              |
| `password`         | Password input           | `#password`    | Just below username                       |
| `sign-in`          | Sign In button           | `#kc-login`    | Below password, full-width inside card    |

These three have real ids — `events.json` `label` will be `username`,
`password`, `kc-login`.

### Home page (Agents)

Recorder viewport: 1920×1080. CSS coords:

| Cue                  | Element                          | Bbox (CSS px)                | Notes                                    |
|---|---|---|---|
| `set-up-a-provider`  | Get-started step 1 button        | x=763 y=11 w=148 h=30        | Top centre of the get-started bar         |
| `providers` (alt)    | Sidebar Providers entry          | x=8 y=89 w=184 h=34          | Left sidebar — alternative path          |

The button's `innerText` is `"1Set up a provider"` (the digit "1" sits
in a small badge inside the button). Token verification will still match
because cue tokens `set up a provider` are present.

### Providers page

| Cue              | Element                  | Bbox (CSS px)             | Notes                                              |
|---|---|---|---|
| `oauth-token`    | "OAuth Token" tab        | x=687 y=290 w=111 h=38    | Default-active tab — shows `claude setup-token` instructions and a `sk-ant-oat-…` input |
| `api-key`        | "API Key" tab            | x=801 y=290 w=78 h=38     | Shows just an `sk-ant-api-…` input — no instructions block |
| `token-input`    | Token/key input          | x=687 y=342 w=425 h=38    | Placeholder changes per tab                         |
| `test`           | Test button              | x=1123 y=342 w=61 h=38    | Disabled until input has content                   |
| `save`           | Save button              | x=1195 y=342 w=80 h=38    | Disabled until input has content                   |

The Anthropic card spans roughly **x=505 y=160 w=480 h=180** in CSS px
(card body without the heading) — useful as a `rect_css` for a
"focus on the card" zoom region.

## Key visual moment to anchor zooms on

**The OAuth-vs-API tab toggle.** Both tabs sit at the centre-top of the
card; clicking between them changes only the input placeholder (and
removes the instructions block when API Key is active). A zoom on the
two tabs + input row is the natural region for the "two ways to add an
Anthropic key" beat.

## Things this exploration deliberately did NOT cover

- Submitting a real key (Test/Save flow). The demo ends before that.
- Logout flow (recording starts from logged-out state, ends without
  logging out).
- Connections / Agents pages (not in scope).
- Settings page.

## Bboxes captured at viewport 1920×1080

(Re-captured after Playwright resize; see screenshots in this folder.)
