export type EventBase = {
  t: number;
  label?: string;
  target?: string;
  // Optional cue name from the speech timings file. If present, the
  // recorder waited until that cue's at_ms before firing this event
  // (or fired late if UI wasn't ready in time — see actualTimings).
  cue?: string;
};

export type ClickEvent = EventBase & {
  kind: "click";
  x: number;
  y: number;
  bbox?: { x: number; y: number; width: number; height: number };
  // Optional: when the page actually visually responded to the click
  // (first screencast frame after mouse.click). Used by the click-effect
  // compositor so the ring lands on the page-response frame, not the
  // click-dispatch frame — they can differ by hundreds of ms on busy
  // pages. Falls back to t when missing.
  effectT?: number;
};

export type MoveEvent = EventBase & {
  kind: "move";
  x: number;
  y: number;
};

export type TypeEvent = EventBase & {
  kind: "type";
  text: string;
  durationMs: number;
};

export type WaitEvent = EventBase & {
  kind: "wait";
  durationMs: number;
  // For semantic waits (waitFor), what we were waiting on.
  reason?: string;
};

export type NavigateEvent = EventBase & {
  kind: "navigate";
  url: string;
};

export type Event =
  | ClickEvent
  | MoveEvent
  | TypeEvent
  | WaitEvent
  | NavigateEvent;

export type EventLog = {
  startedAt: string;
  // CSS layout viewport — coordinates in events are in this space.
  viewport: { width: number; height: number };
  // Raw video frames are at viewport × captureScale (Chromium rasterizes
  // at this density when --force-device-scale-factor is set).
  captureScale: number;
  events: Event[];
};

// Speech-timing schema (TTS pipeline output). Mirrors what tts_edge.py
// and tts_kokoro.py emit so we can read it directly.
export type SpeechCue = { name: string; at_ms: number };
export type SpeechTimings = {
  voice?: string;
  rate?: string;
  duration_ms?: number;
  text?: string;
  words?: { text: string; start_ms: number; end_ms: number }[];
  cues: SpeechCue[];
};

// Per-cue drift report — consumed by the audio assembler to decide
// whether to pad silence around variable-latency segments.
export type CueDrift = {
  name: string;
  intendedAtMs: number;
  actualAtMs: number;
  // Positive = action fired late (UI was slower than narration). Negative
  // shouldn't happen — we always sleep up to the cue.
  driftMs: number;
};

export type ActualTimings = {
  startedAt: string;
  durationMs: number;
  cues: CueDrift[];
};
