# Script — Meet DAM

Dam runs your AI coding agent in its own Kubernetes pod. Credentials
safe, network sandboxed, awake when you're not.

Sign in {{username}} {{kc-login}} and follow three steps to your
first agent.

First, a model provider {{set-up-a-provider}}. Anthropic is supported
today — OpenAI and Google coming soon. Connect via OAuth or API key.
Paste {{token-input}}, test {{test}}, save {{save}}.

Then — connections {{set-up-connections}}. OAuth apps, MCP servers,
custom secrets — every external surface your agents reach, all in
one place. We'll cover these in their own video. Back to the list
{{agents}}.

Last — the agent itself {{add-agent}}. Templates wire up the harness
for you — Claude Code, pi.dev, or roll your own {{claude-code}}.
Give it a name. Toggle which connections and capabilities it's
allowed to use — every agent's reach is scoped explicitly
{{create-agent}}.

Underneath, Dam is spinning up a fresh pod, mounting the credentials
you scoped, and bringing up the harness inside it. Network egress is
locked to the connections you allowed — nothing else is reachable.
When the badge flips green, the agent's ready. Click in
{{agent-row}}.

Now real work. {{prompt-input}} Check Dam repository — who changed
what this week, write me a markdown digest. Send {{send}}, and wait
for the agent's result.

The agent runs inside the pod. No shell on your machine, nothing to
clean up afterwards. When something needs your call, an approval
pops in your inbox — answer it, the agent continues. Your laptop
can sleep; the pod keeps going. The session lives on the platform,
reachable from your phone — or from anyone you share access with,
who can answer those approvals when you're off.

Generated files land right here. Open one {{app-js}} — running code,
inline. Edit it, or add your own. The workspace is a volume that
outlives the pod — your edits are there the next time the agent
wakes up.

Agents you can trust to run unattended. That's Dam.
