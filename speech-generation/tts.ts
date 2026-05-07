// Generate narration audio from a script using ElevenLabs.
//
//   ELEVENLABS_API_KEY=sk_... pnpm tts <script.txt> [voice-id] [out-base]
//   ELEVENLABS_API_KEY=sk_... pnpm tts --run <slug> [voice-id]
//
// In --run mode, reads runs/<slug>/script.md (cues stripped) and writes
// runs/<slug>/speech.mp3.
//
// Otherwise, defaults voice to Brian (free tier) and out-base to the
// script filename without extension. Strips {{cue}} markers from the
// script before sending to TTS — they're metadata for matching cues to
// click events later, not narration content.
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
const CUE_RE = /\{\{[a-z0-9_\-]+\}\}/gi;

// Load .env from cwd if present. Real shell env still wins — values in
// .env only fill missing keys.
const envPath = path.resolve(".env");
if (existsSync(envPath)) process.loadEnvFile(envPath);

function parseCli() {
  const args = process.argv.slice(2);
  let run: string | undefined;
  const positional: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i]!;
    if (a === "--run") {
      run = args[++i];
    } else {
      positional.push(a);
    }
  }
  return { run, positional };
}

async function main() {
  const { run, positional } = parseCli();
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
    console.error("usage: pnpm tts <script.txt> [voice-id] [out-base]");
    console.error("       pnpm tts --run <slug> [voice-id]");
    console.error("  --run <slug>: reads runs/<slug>/script.md, writes runs/<slug>/speech.mp3");
    console.error("  voice-id defaults to Brian (nPczCjzI2devNBz1zQrb, free tier)");
    process.exit(1);
  }

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
  // Strip cue markers and normalise whitespace so the TTS doesn't try
  // to read them aloud.
  const text = raw.replace(CUE_RE, "").replace(/\s+/g, " ").trim();
  if (!text) {
    console.error(`script is empty (or only cues): ${scriptPath}`);
    process.exit(3);
  }

  console.log(`script: ${scriptPath}  (${text.length} chars)`);
  console.log(`voice:  ${voiceId}`);
  console.log(`out:    ${outPath}`);
  console.log("generating…");

  const t0 = Date.now();
  const client = new ElevenLabsClient({ apiKey });
  const response = await client.textToSpeech.convert(voiceId, {
    text,
    modelId: DEFAULT_MODEL,
    outputFormat: DEFAULT_FORMAT,
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
