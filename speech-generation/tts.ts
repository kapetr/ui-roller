// Generate narration audio from a script using ElevenLabs.
//
//   ELEVENLABS_API_KEY=sk_... pnpm tts <script.txt> [voice-id] [out-base]
//   ELEVENLABS_API_KEY=sk_... pnpm tts --run <slug> [voice-id] [--speed 1.1]
//
// In --run mode, reads runs/<slug>/script.md, writes runs/<slug>/speech.mp3,
// and writes runs/<slug>/speech.txt (the cue-and-markdown-stripped text
// actually sent to TTS — useful when handing off to the ElevenLabs UI for
// premium voices).
//
// Otherwise, defaults voice to Brian (free tier) and out-base to the
// script filename without extension.
//
// Pre-processing: strips {{cue}} markers (metadata) and Markdown headers
// (lines starting with `#`) — both are silent in narration. Normalises
// whitespace.
//
// Output: <out-base>.mp3 next to wherever you ran the command from.

import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js";

// Brian — warm conversational male; one of ElevenLabs' pre-made voices,
// which means it works on the free tier. Library/shared voices (e.g.
// Jackson 2zGvynULFssveGrcP8hi) require a paid plan.
const DEFAULT_VOICE = "nPczCjzI2devNBz1zQrb"; // Brian
const DEFAULT_MODEL = "eleven_multilingual_v2";
const DEFAULT_FORMAT = "mp3_44100_128";
// Default a touch above 1.0 — neutral ElevenLabs prosody reads slightly
// slow for product-walkthrough pacing. Override per-run with --speed.
// ElevenLabs clamps to [0.7, 1.2].
const DEFAULT_SPEED = 1.1;
const CUE_RE = /\{\{[a-z0-9_\-]+\}\}/gi;
// Strip markdown headers (lines beginning with # followed by space).
// They're file-organisation metadata, not narration — TTS would read
// them aloud otherwise.
const MD_HEADER_RE = /^#{1,6}[ \t].*$/gm;

// Load .env from cwd if present. Real shell env still wins — values in
// .env only fill missing keys.
const envPath = path.resolve(".env");
if (existsSync(envPath)) process.loadEnvFile(envPath);

function parseCli() {
  const args = process.argv.slice(2);
  let run: string | undefined;
  let speed: number | undefined;
  const positional: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i]!;
    if (a === "--run") {
      run = args[++i];
    } else if (a === "--speed") {
      speed = parseFloat(args[++i] ?? "");
    } else {
      positional.push(a);
    }
  }
  return { run, speed, positional };
}

async function main() {
  const { run, speed: speedArg, positional } = parseCli();
  let scriptPath: string | undefined;
  let voiceArg: string | undefined;
  let outArg: string | undefined;

  if (run) {
    scriptPath = path.resolve("runs", run, "script.md");
    [voiceArg, outArg] = positional;
    if (!outArg) outArg = path.resolve("runs", run, "speech");
  } else {
    [scriptPath, voiceArg, outArg] = positional;
  }

  if (!scriptPath) {
    console.error("usage: pnpm tts <script.txt> [voice-id] [out-base] [--speed 1.1]");
    console.error("       pnpm tts --run <slug> [voice-id] [--speed 1.1]");
    console.error(`  --speed:    voice speed (clamped to 0.7..1.2, default ${DEFAULT_SPEED})`);
    console.error("  --run <slug>: reads runs/<slug>/script.md, writes runs/<slug>/speech.mp3 + speech.txt");
    console.error("  voice-id defaults to Brian (nPczCjzI2devNBz1zQrb, free tier)");
    process.exit(1);
  }
  const speed = Math.max(0.7, Math.min(1.2, speedArg ?? DEFAULT_SPEED));

  const apiKey = process.env.ELEVENLABS_API_KEY;
  if (!apiKey) {
    console.error("ELEVENLABS_API_KEY not set");
    console.error("  export ELEVENLABS_API_KEY=sk_...");
    process.exit(2);
  }

  const voiceId = voiceArg ?? DEFAULT_VOICE;
  const outBase = outArg ?? path.join(
    path.dirname(scriptPath),
    path.basename(scriptPath, path.extname(scriptPath)),
  );
  const outPath = `${outBase}.mp3`;

  const raw = await fs.readFile(scriptPath, "utf8");
  // Strip cue markers + Markdown headers, normalise whitespace, then
  // remove orphan spaces before punctuation (e.g. "Sign in , and" →
  // "Sign in, and") that show up when stripped cues were the only thing
  // between a word and a comma/period.
  const text = raw
    .replace(MD_HEADER_RE, "")
    .replace(CUE_RE, "")
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();
  if (!text) {
    console.error(`script is empty (or only cues/headers): ${scriptPath}`);
    process.exit(3);
  }

  // In --run mode, also drop the cleaned text alongside the mp3 so the
  // user can copy it into ElevenLabs' UI for a premium voice.
  if (run) {
    await fs.writeFile(`${outBase}.txt`, text + "\n");
  }

  console.log(`script: ${scriptPath}  (${text.length} chars)`);
  console.log(`voice:  ${voiceId}`);
  console.log(`speed:  ${speed.toFixed(2)}`);
  console.log(`out:    ${outPath}`);
  console.log("generating…");

  const t0 = Date.now();
  const client = new ElevenLabsClient({ apiKey });
  const response = await client.textToSpeech.convert(voiceId, {
    text,
    modelId: DEFAULT_MODEL,
    outputFormat: DEFAULT_FORMAT,
    voiceSettings: { speed },
  });

  // The SDK returns either a ReadableStream or something Buffer.from
  // can wrap, depending on version. Normalise via Response.arrayBuffer.
  const audio = Buffer.from(
    await new Response(response as unknown as BodyInit).arrayBuffer(),
  );

  await fs.writeFile(outPath, audio);
  const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
  const kb = (audio.length / 1024).toFixed(0);
  console.log(`✓ ${outPath}  (${kb} KB, ${elapsed}s)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
