# Zoom intent — DAM, add Anthropic provider

Where the camera should focus, in plain English. Resolved against the
actual recording in `zoom-plan.json`.

## Wide

- Opening intro (DAM tagline) — wide, the home page is mostly empty.
- All navigations between login → home → providers — wide, page is
  changing.
- Closing line ("ready for connections and agents") — wide, viewer
  doesn't need to see anything specific.

## Zoom-in

1. **Login form**, ~1.5×, while the user types `dev`/`dev` and clicks
   Sign In. Surrounding chrome is empty; the form is the only thing
   that matters. Camera centre falls naturally on the form by
   averaging the bbox centres of the username and Sign In clicks.

2. **Provider credential tabs + input row**, ~1.5×, while narration
   covers the "two ways to add your credential" beat. The OAuth Token
   tab is already active and never gets clicked, so the camera ramps
   in over the OAuth-Token narration and lands at peak when the user
   clicks API Key. Holds through the closing API-key line, then
   ramps out before "Pick the tab that matches…".

   `rect_css` set explicitly to the tabs+input row bbox — this avoids
   the centre being pulled around by the user's stray clicks during
   exploration of the credential card.
