// Generate narration audio from a script using ElevenLabs.
//
//   ELEVENLABS_API_KEY=sk_... pnpm tts <script.txt> [voice-id] [out-base]
//
// Defaults voice to Jackson (2zGvynULFssveGrcP8hi) and out-base to the
// script filename without extension. Strips {{cue}} markers from the
// script before sending to TTS — they're metadata for scripted-scene
// alignment, not narration content. For the manual-recording workflow
// you don't need cues; just write plain narration text.
//
// Output: <out-base>.mp3 next to wherever you ran the command from.

import fs from "node:fs/promises";
import path from "node:path";
import { ElevenLabsClient } from "@elevenlabs/elevenlabs-js";

const DEFAULT_VOICE = "2zGvynULFssveGrcP8hi"; // Jackson
const DEFAULT_MODEL = "eleven_multilingual_v2";
const DEFAULT_FORMAT = "mp3_44100_128";
const CUE_RE = /\{\{[a-z0-9_\-]+\}\}/gi;

async function main() {
  const [scriptPath, voiceArg, outArg] = process.argv.slice(2);
  if (!scriptPath) {
    console.error("usage: pnpm tts <script.txt> [voice-id] [out-base]");
    console.error("  voice-id defaults to Jackson (2zGvynULFssveGrcP8hi)");
    console.error("  out-base defaults to <script-without-extension>");
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
