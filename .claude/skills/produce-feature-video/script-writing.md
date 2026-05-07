# Writing the narration script

**Audience: the video viewer, not the recorder.** They can see clicks
already; the audio's job is to teach what the product is, why it
matters, and what's happening underneath.

The two failure modes below catch most weak first drafts. Fix them
before showing the script to the user.

## Failure 1 — narrating clicks the viewer can already see

Bad:

> Click Save. Now you're back on the agents page. Click Add Agent.

The screen shows all of this. The audio adds nothing. You've burned
ten seconds telling the viewer what their eyes already told them.

Better — replace each click sentence with what's *interesting* about
the moment. The cue marker still goes where the click happens; it's
invisible to the listener.

| Click | Narrating (bad) | Selling (better) |
|---|---|---|
| Save provider key | "Click Save." | "Stored encrypted, scoped per agent, out of your shell history." |
| Open Connections page | "Now the connections page." | "Every external surface your agents reach, all in one place." |
| Open Add Agent | "Click Add Agent." | "Templates wire up the harness for you — Claude Code, pi.dev, or roll your own." |
| Click into agent | "Click in." | "When the badge flips green, the agent's ready." |

For each beat ask: *what's the viewer learning?* If the answer is
"where the cursor's going", rewrite. If the answer is "what the
product does, plus visual confirmation", you're there.

This isn't pure marketing puff — concrete claims (encrypted, scoped,
sandboxed, isolated) carry weight. Vague claims (powerful, easy,
intuitive) read as filler. Stick to specifics the UI is *about* to
demonstrate.

## Failure 2 — dead air during long waits

Most demos have at least one beat where the user clicks and then
waits — pod provisioning, model streaming, build pipelines, data
syncs. If the script doesn't cover the wait, the audio ends and the
viewer stares at a spinner.

Write substantive narration for every beat that takes >5s of real
time. These are your highest-value seconds: the UI is paused, the
viewer's attention is captive, and the audio has no on-screen action
competing for it.

Pattern: explain what's happening *underneath*. Architecture.
Tradeoffs. Why it's worth waiting. The wait turns into a teaching
moment instead of a stall.

Example — pod provisioning (~10–30s real wait):

> Underneath, DAM is spinning up a fresh pod, mounting the credentials
> you scoped, and bringing up the harness inside it. Network egress
> is locked to the connections you allowed — nothing else is
> reachable. When the badge flips green, the agent's ready.

Example — model thinking and writing files (~30–90s real wait):

> The agent runs inside the pod. No shell on your machine, no leaked
> secrets, nothing to clean up afterwards. It can keep working while
> your laptop sleeps, through context switches, through the night.
> When it's done, the files land in the workspace.

These also happen to be the two moments where viewers are most likely
to drop off — and the moments where you can land the strongest
product claims uncontested. Don't waste them.

**Warn the user up front**: wait segments almost always need a manual
time-stretch in Resolve, because the real-world wait rarely matches
the narration exactly. The audio is the spine; the video gets nudged
to fit. This is expected and easy to do in post — but they should
plan for the manual pass.

## Hook + outro

- **Hook** (~8s, opening): state what the product is and the promise.
  One short sentence per claim. No clicks yet.
- **Outro** (~3s, closing): one-line value summary, then sign-off. No
  clicks.

These bookend the demo and are likely to end up as thumbnail copy or
pull-quotes. Make them quotable.

## Length budget

- 60–120s is the comfortable range for a walkthrough.
- TTS at speed 1.1 reads ~3 words/sec with natural pauses; target
  ~200–310 words for a 90s video.
- The wait-filler beats add words without adding perceived length —
  on-screen action lags the narration. Don't be precious about word
  count if the script is mostly substance.

## Read it aloud

Before showing the user, read every sentence aloud to yourself. If a
clause makes you breathe mid-sentence, split it. If two adjacent
sentences feel too clipped, merge them. TTS surfaces the same
problems with worse prosody, so it's cheaper to fix here.
