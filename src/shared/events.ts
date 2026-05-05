export type EventBase = {
  t: number;
  label?: string;
  target?: string;
};

export type ClickEvent = EventBase & {
  kind: "click";
  x: number;
  y: number;
  bbox?: { x: number; y: number; width: number; height: number };
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
