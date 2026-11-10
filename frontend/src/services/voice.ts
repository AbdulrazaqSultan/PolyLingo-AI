import type { SpeechResult } from "../types";
export type VoicePhase =
  | "idle"
  | "recording"
  | "uploading"
  | "transcribing"
  | "correcting"
  | "translating"
  | "synthesizing"
  | "complete"
  | "error";
export type VoiceEvent =
  | {
      event: "raw_transcript";
      data: {
        raw_transcript: string;
        detected_language: string;
        stt_ms: number;
      };
    }
  | { event: "stage"; stage: VoicePhase }
  | { event: "transcript" | "translation" | "result"; data: SpeechResult }
  | { event: "error"; detail: string };
export type VoiceOptions = {
  source: string | null;
  target: string;
  generate_voice: boolean;
  voice: string;
  speed: number;
};
export async function requestVoice(
  blob: Blob,
  options: VoiceOptions,
  signal: AbortSignal,
  onEvent: (event: VoiceEvent) => void,
) {
  const body = new FormData();
  body.append("file", blob, "recording.audio");
  if (options.source) body.append("source", options.source);
  body.append("target", options.target);
  body.append("generate_voice", String(options.generate_voice));
  body.append("speed", String(options.speed));
  if (options.voice) body.append("voice", options.voice);
  const response = await fetch("/api/speech/translate?stream=true", {
    method: "POST",
    body,
    signal,
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Service is unreachable." }));
    throw new Error(error.detail);
  }
  if (!response.body) throw new Error("Speech streaming is unavailable.");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = "",
    finished = false;
  function consume(line: string) {
    if (!line.trim()) return;
    const event = JSON.parse(line) as VoiceEvent;
    if (event.event === "error") throw new Error(event.detail);
    if (event.event === "result") finished = true;
    onEvent(event);
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      lines.forEach(consume);
      if (done) break;
    }
    consume(buffer);
    if (!finished)
      throw new Error("The speech stream ended before completion.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
export function speechAudioURL(value: string): string {
  if (
    !/^data:audio\/mpeg;base64,[A-Za-z0-9+/=]+$/.test(value) ||
    value.length > 8_000_000
  )
    throw new Error("Invalid speech audio response.");
  const bytes = Uint8Array.from(atob(value.split(",")[1]), (c) =>
    c.charCodeAt(0),
  );
  return URL.createObjectURL(new Blob([bytes], { type: "audio/mpeg" }));
}
