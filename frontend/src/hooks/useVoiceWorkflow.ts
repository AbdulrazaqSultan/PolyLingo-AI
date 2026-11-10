import { useEffect, useReducer, useRef } from "react";
import {
  requestVoice,
  type VoiceOptions,
  type VoicePhase,
} from "../services/voice";
import type { SpeechResult } from "../types";

type State = { phase: VoicePhase; requestId: number };
type Action =
  | { type: "start"; requestId: number }
  | { type: "phase"; requestId: number; phase: VoicePhase }
  | { type: "cancel"; requestId: number };
const transitions: Record<VoicePhase, VoicePhase[]> = {
  idle: ["uploading"],
  recording: ["uploading"],
  uploading: ["transcribing", "error"],
  transcribing: ["correcting", "error"],
  correcting: ["translating", "complete", "error"],
  translating: ["synthesizing", "complete", "error"],
  synthesizing: ["complete", "error"],
  complete: [],
  error: [],
};
export function voiceReducer(state: State, action: Action): State {
  if (action.type === "start")
    return { phase: "uploading", requestId: action.requestId };
  if (action.type === "cancel")
    return { phase: "idle", requestId: action.requestId };
  if (action.requestId !== state.requestId) return state;
  if (!transitions[state.phase].includes(action.phase)) return state;
  return { ...state, phase: action.phase };
}
type Callbacks = {
  onRawTranscript?: (data: {
    raw_transcript: string;
    detected_language: string;
    stt_ms: number;
  }) => void;
  onStart: () => void;
  onTranscript: (result: SpeechResult) => void;
  onTranslation: (result: SpeechResult) => void;
  onResult: (result: SpeechResult) => void;
  onError: (message: string) => void;
};
export function useVoiceWorkflow(callbacks: Callbacks) {
  const [state, dispatch] = useReducer(voiceReducer, {
    phase: "idle",
    requestId: 0,
  });
  const sequence = useRef(0),
    controller = useRef<AbortController | null>(null),
    handlers = useRef(callbacks);
  handlers.current = callbacks;
  useEffect(
    () => () => {
      sequence.current++;
      controller.current?.abort();
    },
    [],
  );
  function cancel() {
    sequence.current++;
    controller.current?.abort();
    dispatch({ type: "cancel", requestId: sequence.current });
  }
  async function run(blob: Blob, options: VoiceOptions) {
    controller.current?.abort();
    const requestId = ++sequence.current,
      current = new AbortController();
    controller.current = current;
    handlers.current.onStart();
    dispatch({ type: "start", requestId });
    try {
      await requestVoice(blob, options, current.signal, (event) => {
        if (sequence.current !== requestId || current.signal.aborted) return;
        if (event.event === "stage")
          dispatch({ type: "phase", requestId, phase: event.stage });
        else if (event.event === "raw_transcript")
          handlers.current.onRawTranscript?.(event.data);
        else if (event.event === "transcript")
          handlers.current.onTranscript(event.data);
        else if (event.event === "translation")
          handlers.current.onTranslation(event.data);
        else if (event.event === "result") {
          handlers.current.onResult(event.data);
          dispatch({
            type: "phase",
            requestId,
            phase:
              event.data.translation_status === "error" ? "error" : "complete",
          });
        }
      });
    } catch (error) {
      if (sequence.current !== requestId || current.signal.aborted) return;
      handlers.current.onError((error as Error).message);
      dispatch({ type: "phase", requestId, phase: "error" });
    }
  }
  return {
    ...state,
    busy: !["idle", "complete", "error"].includes(state.phase),
    run,
    cancel,
  };
}
