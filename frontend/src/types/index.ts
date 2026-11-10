export type Language = {
  name: string;
  native: string;
  iso: string;
  nllb: string;
  direction: "rtl" | "ltr";
};
export type HistoryItem = {
  id: string;
  text: string;
  translated_text: string;
  source: string;
  target: string;
  provider: string;
  translation_ms: number;
  mode: string;
  timestamp: string;
  status: string;
  raw_transcript?: string;
  corrected_transcript?: string;
  detected_language?: string;
  correction_provider?: string;
  correction_status?: string;
  total_ms?: number;
};

export type SpeechResult = {
  detected_language: string;
  raw_transcript: string;
  corrected_transcript: string;
  correction_applied: boolean;
  correction_status: string;
  correction_provider: string;
  source: string;
  target: string;
  translated_text: string;
  provider: string;
  fallback_used: boolean;
  translation_ms: number;
  translation_status: "complete" | "error" | "manual" | "same_language";
  tts_status: string;
  audio_url: string | null;
  error: string | null;
  tts_error: string | null;
  timings: {
    asr_ms: number;
    correction_ms: number;
    translation_ms: number;
    tts_ms: number;
    total_ms: number;
  };
};
