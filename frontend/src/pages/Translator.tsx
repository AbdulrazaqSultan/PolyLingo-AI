import { useI18n, LanguageSwitcher } from "../i18n";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowLeftRight,
  AudioLines,
  Check,
  ChevronRight,
  Copy,
  Download,
  FileAudio,
  Globe2,
  History,
  Mic,
  RotateCcw,
  Sparkles,
  Square,
  Trash2,
  Type,
  Volume2,
  X,
  Activity,
  Layers,
  ShieldCheck,
} from "lucide-react";
import Network from "../components/Network";
import { api, synthesize } from "../services/api";
import { useRecorder } from "../hooks/useRecorder";
import { useVoiceWorkflow } from "../hooks/useVoiceWorkflow";
import { speechAudioURL } from "../services/voice";
import type { HistoryItem, Language, SpeechResult } from "../types";
const stages = [
  "Speech recognition",
  "Transcript refinement",
  "Neural translation",
  "Speech synthesis",
];
export default function Translator() {
  const { t, locale } = useI18n();
  const [languages, setLanguages] = useState<Language[]>([]),
    [config, setConfig] = useState<any>({});
  const [source, setSource] = useState(""),
    [target, setTarget] = useState(""),
    [mode, setMode] = useState("text");
  const [text, setText] = useState(""),
    [result, setResult] = useState(""),
    [provider, setProvider] = useState(""),
    [manualStatus, setStatus] = useState(""),
    [error, setError] = useState("");
  const [audio, setAudio] = useState(""),
    [metrics, setMetrics] = useState<Record<string, number>>({}),
    [history, setHistory] = useState<HistoryItem[]>([]),
    [showHistory, setShowHistory] = useState(false);
  const [voices, setVoices] = useState<
      {
        id: string;
        name: string;
      }[]
    >([]),
    [voice, setVoice] = useState(""),
    [speed, setSpeed] = useState(0),
    [voiceEnabled, setVoiceEnabled] = useState(true),
    [autoDetect, setAutoDetect] = useState(false),
    [copied, setCopied] = useState(false);
  const [pipelineInfo, setPipelineInfo] = useState(1);
  const [transcript, setTranscript] = useState<SpeechResult | null>(null),
    [lastTranslatedInput, setLastTranslatedInput] = useState("");
  const audioRef = useRef<HTMLAudioElement>(null),
    audioUrl = useRef(""),
    fileRef = useRef<HTMLInputElement>(null);
  function changeAudio(url: string) {
    if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
    audioUrl.current = url;
    setAudio(url);
  }
  useEffect(() => {
    Promise.all([api<Language[]>("/languages"), api("/config")])
      .then(([langs, opts]) => {
        setLanguages(langs);
        setConfig(opts);
        setSource(
          langs.some((l) => l.iso === opts.default_source)
            ? opts.default_source
            : langs[0]?.iso || "",
        );
        setTarget(
          langs.some((l) => l.iso === opts.default_target)
            ? opts.default_target
            : langs[1]?.iso || langs[0]?.iso || "",
        );

        if (opts.history_enabled) {
          try {
            setHistory(
              JSON.parse(localStorage.getItem("polylingo-history") || "[]"),
            );
          } catch {
            localStorage.removeItem("polylingo-history");
          }
        }
      })
      .catch((e) => setError(e.message));
    return () => {
      if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
    };
  }, []);
  useEffect(() => {
    setVoice("");
    setVoices([]);
    if (target)
      api("/speech/voices?language=" + target)
        .then(setVoices)
        .catch(() => {});
  }, [target]);
  function saveHistory(item: HistoryItem) {
    if (!config.history_enabled) return;
    setHistory((current) => {
      const next = [item, ...current].slice(0, 40);
      try {
        localStorage.setItem("polylingo-history", JSON.stringify(next));
      } catch {
        setError("Browser history storage is full. Clear older entries.");
      }
      return next;
    });
  }
  const voiceWorkflow = useVoiceWorkflow({
    onRawTranscript(data) {
      setText(data.raw_transcript);
      setSource(data.detected_language);
      setMetrics({ stt: data.stt_ms });
    },
    onStart() {
      setError("");
      setText("");
      setTranscript(null);
      setResult("");
      setMetrics({});
      setLastTranslatedInput("");
      changeAudio("");
    },
    onTranscript(data) {
      setText(data.corrected_transcript);
      setSource(data.detected_language);
      setTranscript(data);
      setMetrics({
        stt: data.timings.asr_ms,
        correction: data.timings.correction_ms,
      });
    },
    onTranslation(data) {
      setResult(data.translated_text);
      setProvider(data.provider);
      setLastTranslatedInput(data.corrected_transcript);
    },
    onResult(data) {
      setMetrics({
        stt: data.timings.asr_ms,
        correction: data.timings.correction_ms,
        translation: data.timings.translation_ms,
        tts: data.timings.tts_ms,
        total: data.timings.total_ms,
      });
      if (data.audio_url) changeAudio(speechAudioURL(data.audio_url));
      if (data.error || data.tts_error)
        setError(data.error || data.tts_error || "");
      if (data.translation_status === "same_language")
        setError("Choose a different target language to translate speech.");
      if (["complete", "error"].includes(data.translation_status))
        saveHistory({
          id: crypto.randomUUID(),
          text: data.corrected_transcript,
          raw_transcript: data.raw_transcript,
          corrected_transcript: data.corrected_transcript,
          detected_language: data.detected_language,
          correction_provider: data.correction_provider,
          correction_status: data.correction_status,
          translated_text: data.translated_text,
          source: data.source,
          target: data.target,
          provider: data.provider,
          translation_ms: data.translation_ms,
          total_ms: data.timings.total_ms,
          mode: "speech",
          timestamp: new Date().toISOString(),
          status: data.translation_status === "complete" ? "success" : "error",
        });
    },
    onError: setError,
  });
  const status =
    manualStatus ||
    (
      {
        uploading: "Uploading audio",
        transcribing: "Transcribing",
        correcting: "Refining transcript",
        translating: "Translating",
        synthesizing: "Generating voice",
      } as Record<string, string>
    )[voiceWorkflow.phase] ||
    "";
  const busy = !!manualStatus || voiceWorkflow.busy;
  const manualDirty =
    mode !== "text" && !!lastTranslatedInput && text !== lastTranslatedInput;
  async function transcribe(blob: Blob) {
    if (
      !languages.some((l) => l.iso === target) ||
      (!autoDetect && !languages.some((l) => l.iso === source))
    ) {
      setError("Choose valid source and target languages.");
      return;
    }
    await voiceWorkflow.run(blob, {
      source: autoDetect ? null : source,
      target,
      generate_voice: voiceEnabled,
      voice,
      speed,
    });
  }
  const recorder = useRecorder(
    transcribe,
    setError,
    config.max_audio_seconds || 60,
  );
  async function generateSpeech(output = result) {
    setStatus("Generating voice");
    try {
      const data = await synthesize({
        text: output,
        language: target,
        voice: voice || null,
        speed,
      });
      changeAudio(data.url);
      setMetrics((m) => ({ ...m, tts: data.ms }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStatus("");
    }
  }
  async function translate() {
    voiceWorkflow.cancel();
    setError("");
    setResult("");
    changeAudio("");
    setStatus("Translating");
    const start = performance.now();
    try {
      const data = await api("/translate", {
        method: "POST",
        body: JSON.stringify({
          text,
          source,
          target,
          mode: mode === "text" ? "text" : "speech",
        }),
      });
      setResult(data.translated_text);
      setLastTranslatedInput(text);
      setProvider(data.provider + (data.fallback_used ? " · fallback" : ""));
      setMetrics((m) => ({ ...m, translation: data.translation_ms }));
      saveHistory({
        id: crypto.randomUUID(),
        text,
        source,
        target,
        translated_text: data.translated_text,
        provider: data.provider,
        translation_ms: data.translation_ms,
        mode,
        timestamp: new Date().toISOString(),
        status: "success",
        ...(mode !== "text" && transcript
          ? {
              raw_transcript: transcript.raw_transcript,
              corrected_transcript: text,
              detected_language: source,
              correction_provider: transcript.correction_provider,
            }
          : {}),
      });
      if (voiceEnabled) await generateSpeech(data.translated_text);
    } catch (e) {
      setError((e as Error).message);
      saveHistory({
        id: crypto.randomUUID(),
        text,
        source,
        target,
        translated_text: "",
        provider: "unavailable",
        translation_ms: performance.now() - start,
        mode,
        timestamp: new Date().toISOString(),
        status: "error",
      });
    } finally {
      setMetrics((m) => ({
        ...m,
        total: performance.now() - start + (m.stt || 0),
      }));
      setStatus("");
    }
  }
  const sourceLanguage = languages.find((l) => l.iso === source),
    targetLanguage = languages.find((l) => l.iso === target);
  useEffect(() => {
    if (audio && config.autoplay) void audioRef.current?.play().catch(() => {});
  }, [audio, config.autoplay]);
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Copy is unavailable in this browser.");
    }
  }
  return (
    <div className="public-app">
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-icon">
            <AudioLines size={21} />
          </span>
          PolyLingo<span className="brand-ai">AI</span>
        </a>
        <nav>
          <a href="#translator">{t("Workspace")}</a>
          <a href="#pipeline">{t("The pipeline")}</a>
          <a href="#research">{t("Research")}</a>
        </nav>
        <span className="header-note">
          <i />
          {t("Built on neural intelligence")}
        </span>
        <LanguageSwitcher />
      </header>
      <main>
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <span />
              {t("FOUR LANGUAGES. ONE CONNECTION.")}
            </div>
            <h1>
              {t("Speak naturally.")}
              <br />
              <span>{t("Understand globally.")}</span>
            </h1>
            <p>
              {t(
                "Ideas deserve to travel. Turn your words into another language with intelligent speech recognition, neural translation, and natural voices.",
              )}
            </p>
            <div className="hero-actions">
              <a className="primary" href="#translator">
                {t("Start translating")}
                <ArrowRight size={17} />
              </a>
              <a className="text-link" href="#pipeline">
                {t("Explore the AI pipeline")}
                <ChevronRight size={16} />
              </a>
            </div>
            <div className="hero-proof">
              <span>
                <Layers size={14} /> NLLB + LoRA
              </span>
              <span>
                <Globe2 size={14} />
                {t("12 translation directions")}
              </span>
              <span>
                <AudioLines size={14} />
                {t("Text & voice")}
              </span>
            </div>
          </div>
          <Network />
        </section>
        <section id="translator" className="workspace">
          <div className="section-heading">
            <div>
              <div className="eyebrow">{t("YOUR MULTILINGUAL WORKSPACE")}</div>
              <h2>{t("A thought. A voice. A new language.")}</h2>
            </div>
            <button className="secondary" onClick={() => setShowHistory(true)}>
              <History size={16} />
              {t("History")} {history.length > 0 && <b>{history.length}</b>}
            </button>
          </div>
          <div className="console">
            <div className="console-toolbar">
              <div className="tabs">
                {[
                  { id: "text", icon: Type, label: t("Text") },
                  { id: "voice", icon: Mic, label: t("Voice") },
                  { id: "file", icon: FileAudio, label: t("Audio file") },
                ].map(({ id, icon: Icon, label }) => (
                  <button
                    key={id}
                    disabled={busy || recorder.recording}
                    className={mode === id ? "active" : ""}
                    onClick={() => setMode(id)}
                  >
                    <Icon size={16} />
                    {label}
                  </button>
                ))}
              </div>
              <span className="console-label">
                <span className="tiny-dot" />
                {t("NEURAL TRANSLATION ENGINE")}
              </span>
            </div>
            <div className="language-bar">
              <div>
                <span className="small-label">{t("TRANSLATE FROM")}</span>
                <select
                  aria-label={t("Source language")}
                  value={source}
                  disabled={busy || recorder.recording}
                  onChange={(e) => setSource(e.target.value)}
                >
                  {languages.map((l) => (
                    <option key={l.iso} value={l.iso}>
                      {t(l.name)} · {l.native}
                    </option>
                  ))}
                </select>
              </div>
              <button
                className="swap icon-button"
                aria-label={t("Swap languages")}
                disabled={busy || recorder.recording}
                onClick={() => {
                  setSource(target);
                  setTarget(source);
                  setText(result || text);
                  setResult("");
                  changeAudio("");
                }}
              >
                <ArrowLeftRight size={18} />
              </button>
              <div>
                <span className="small-label">{t("TRANSLATE TO")}</span>
                <select
                  aria-label={t("Target language")}
                  value={target}
                  disabled={busy || recorder.recording}
                  onChange={(e) => {
                    setTarget(e.target.value);
                    setResult("");
                    changeAudio("");
                  }}
                >
                  {languages.map((l) => (
                    <option key={l.iso} value={l.iso}>
                      {t(l.name)} · {l.native}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {mode !== "text" && (
              <div className="voice-panel">
                <div className="voice-capture">
                  <button
                    className={
                      "mic-button " + (recorder.recording ? "recording" : "")
                    }
                    aria-label={
                      recorder.recording
                        ? t("Stop recording")
                        : t("Start recording")
                    }
                    disabled={!!manualStatus}
                    onClick={() =>
                      recorder.recording
                        ? recorder.stop()
                        : (voiceWorkflow.cancel(), void recorder.start())
                    }
                  >
                    {recorder.recording ? (
                      <Square size={22} />
                    ) : mode === "file" ? (
                      <FileAudio size={24} />
                    ) : (
                      <Mic size={24} />
                    )}
                  </button>
                  <div>
                    <strong>
                      {recorder.recording
                        ? t("Listening\u2026")
                        : mode === "voice"
                          ? t("Your voice, without borders")
                          : t("Bring your audio into the conversation")}
                    </strong>
                    <p>
                      {recorder.recording
                        ? `${recorder.seconds}${t("s")} / ${config.max_audio_seconds || 60}${t("s")} · ${t("Tap to stop")}`
                        : t(
                            config.auto_translate_voice === false
                              ? "Record or upload, then review the transcription."
                              : "Record or upload. Refinement and translation continue automatically.",
                          )}
                    </p>
                  </div>
                  <div className="waveform">
                    {recorder.levels.map((v, i) => (
                      <i
                        key={i}
                        style={{
                          height:
                            (recorder.recording
                              ? v * 42
                              : 8 + Math.sin(i * 1.6) * 5) + "px",
                        }}
                      />
                    ))}
                  </div>
                </div>
                <div className="upload-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={autoDetect}
                      onChange={(e) => setAutoDetect(e.target.checked)}
                    />{" "}
                    {t("Detect source language")}
                  </label>
                  <button
                    className="text-link"
                    disabled={busy || recorder.recording}
                    onClick={() => fileRef.current?.click()}
                  >
                    {t("Upload audio")}
                    <ArrowRight size={14} />
                  </button>
                  <input
                    hidden
                    ref={fileRef}
                    type="file"
                    accept="audio/*,.webm"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void transcribe(f);
                      e.target.value = "";
                    }}
                  />
                </div>
              </div>
            )}
            <div className="text-panes">
              <div className="text-pane">
                <div className="pane-top">
                  <span>
                    {mode === "text"
                      ? t("SOURCE TEXT")
                      : t("RECOGNIZED SPEECH \u00B7 EDITABLE")}
                  </span>
                  <button
                    aria-label={t("Clear input")}
                    className="icon-button"
                    disabled={!!manualStatus}
                    onClick={() => {
                      voiceWorkflow.cancel();
                      setTranscript(null);
                      setLastTranslatedInput("");
                      setText("");
                      setResult("");
                      changeAudio("");
                      setMetrics({});
                    }}
                  >
                    <X size={15} />
                  </button>
                </div>
                <textarea
                  aria-label={t("Source text")}
                  dir={sourceLanguage?.direction || "auto"}
                  placeholder={t(
                    "Every connection starts with a few words\u2026",
                  )}
                  value={text}
                  maxLength={config.max_text_length || 2000}
                  onChange={(e) => setText(e.target.value)}
                  readOnly={[
                    "uploading",
                    "transcribing",
                    "correcting",
                  ].includes(voiceWorkflow.phase)}
                  disabled={!!manualStatus}
                />
                {mode !== "text" && transcript && (
                  <div className="transcript-refinement">
                    {transcript.correction_applied && (
                      <span className="refinement-badge">
                        <Check size={13} />
                        {t("Transcript refined")}
                      </span>
                    )}
                    {transcript.correction_status === "fallback" && (
                      <span className="muted">
                        {t("Original transcript retained")}
                      </span>
                    )}
                    <details>
                      <summary>{t("View original transcript")}</summary>
                      <strong>{t("Original")}</strong>
                      <p dir={sourceLanguage?.direction}>
                        {transcript.raw_transcript}
                      </p>
                      <strong>{t("Corrected")}</strong>
                      <p dir={sourceLanguage?.direction}>
                        {transcript.corrected_transcript}
                      </p>
                    </details>
                  </div>
                )}
                <div className="pane-bottom">
                  <span>
                    {text.length.toLocaleString()} /{" "}
                    {(config.max_text_length || 2000).toLocaleString()}
                  </span>
                  <span>{t("Short passages work best")}</span>
                </div>
              </div>
              <div className={"text-pane output " + (busy ? "processing" : "")}>
                <div className="pane-top">
                  <span>
                    <Sparkles size={13} />
                    {t("TRANSLATION")}
                  </span>
                  {result && (
                    <button
                      className="icon-button"
                      aria-label={t("Copy translation")}
                      onClick={() => void copy(result)}
                    >
                      {copied ? <Check size={15} /> : <Copy size={15} />}
                    </button>
                  )}
                </div>
                <div
                  className="translation-output"
                  dir={targetLanguage?.direction || "auto"}
                  aria-live="polite"
                >
                  {result || (
                    <span className="placeholder">
                      {t(status || "A new language. The same meaning.")}
                    </span>
                  )}
                </div>
                <div className="pane-bottom">
                  <span>
                    {provider ||
                      t("Powered by your fine-tuned PolyLingo model")}
                  </span>
                  {result && <Check size={14} />}
                </div>
              </div>
            </div>
            <div className="console-footer">
              {voiceWorkflow.busy && (
                <button
                  className="text-link"
                  onClick={() => voiceWorkflow.cancel()}
                >
                  {t("Cancel processing")}
                </button>
              )}
              <label className="voice-toggle">
                <input
                  type="checkbox"
                  checked={voiceEnabled}
                  onChange={(e) => setVoiceEnabled(e.target.checked)}
                />
                <Volume2 size={15} />
                {t("Generate translated speech")}
              </label>
              <button
                className="primary"
                disabled={
                  busy ||
                  recorder.recording ||
                  !text.trim() ||
                  !source ||
                  !target
                }
                onClick={() => void translate()}
              >
                {busy ? <span className="spinner" /> : <Sparkles size={16} />}{" "}
                {t(
                  status ||
                    (manualDirty ? "Translate edited text" : "Translate"),
                )}{" "}
                {!busy && <ArrowRight size={16} />}
              </button>
            </div>
            {error && (
              <div role="alert" className="error">
                <Activity size={16} />
                {t(error)}
                <button
                  aria-label={t("Dismiss error")}
                  onClick={() => setError("")}
                >
                  <X size={15} />
                </button>
              </div>
            )}
            {(audio || result) && (
              <div className="audio-output">
                <Volume2 size={19} />
                <div className="audio-detail">
                  <strong>
                    {t("Hear it in")} {t(targetLanguage?.name || "")}
                  </strong>
                  {audio ? (
                    <audio ref={audioRef} controls src={audio} />
                  ) : (
                    <button
                      className="text-link"
                      disabled={busy}
                      onClick={() => void generateSpeech()}
                    >
                      {t("Generate voice")}
                    </button>
                  )}
                </div>
                {audio && (
                  <a
                    href={audio}
                    download="polylingo-translation.mp3"
                    className="icon-button"
                    aria-label={t("Download translated audio")}
                  >
                    <Download size={17} />
                  </a>
                )}
                <select
                  aria-label={t("Voice")}
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                >
                  <option value="">{t("Default voice")}</option>
                  {voices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
                </select>
                <label className="speed">
                  {t("Speed")}
                  <select
                    aria-label={t("Speech speed")}
                    value={speed}
                    onChange={(e) => setSpeed(Number(e.target.value))}
                  >
                    <option value={-25}>0.75×</option>
                    <option value={0}>1×</option>
                    <option value={25}>1.25×</option>
                    <option value={50}>1.5×</option>
                  </select>
                </label>
              </div>
            )}
          </div>
          <div className="inference-strip">
            <span>
              <ShieldCheck size={14} />
              {t("History stays in this browser")}
            </span>
            <div>
              {stages.map((stage, i) => (
                <span
                  key={t(stage)}
                  className={
                    status
                      .toLowerCase()
                      .includes(["transcrib", "refin", "translat", "voice"][i])
                      ? "stage-active"
                      : ""
                  }
                >
                  <i />
                  {t(stage)}
                  {metrics[["stt", "correction", "translation", "tts"][i]] !==
                    undefined && (
                    <b>
                      {Math.round(
                        metrics[["stt", "correction", "translation", "tts"][i]],
                      )}{" "}
                      {t("ms")}
                    </b>
                  )}
                  {i < 3 && <ChevronRight size={12} />}
                </span>
              ))}
            </div>
            {metrics.total !== undefined && (
              <span>
                {t("Total")} {Math.round(metrics.total)} {t("ms")}
              </span>
            )}
          </div>
        </section>
        {!busy && voiceWorkflow.phase === "complete" && (
          <p className="voice-ready" role="status">
            {t("Ready")}
          </p>
        )}
        <section id="pipeline" className="pipeline-section">
          <div className="section-heading">
            <div>
              <div className="eyebrow">{t("BEHIND EVERY CONNECTION")}</div>
              <h2>{t("Intelligence at every step.")}</h2>
            </div>
            <p>
              {t("Three specialized engines.")}
              <br />
              {t("One seamless conversation.")}
            </p>
          </div>
          <div className="pipeline-cards">
            {[
              {
                icon: Mic,
                title: t("Listen"),
                tag: t("01 / SPEECH RECOGNITION"),
                body: t(
                  "Whisper turns spoken language into editable text. Choose your language, or let the model detect it.",
                ),
                tech: t("Whisper \u00B7 Local inference"),
              },
              {
                icon: Layers,
                title: t("Understand"),
                tag: t("02 / NEURAL TRANSLATION"),
                body: t(
                  "Your words pass through NLLB, fine-tuned with LoRA to carry meaning across four languages.",
                ),
                tech: "NLLB-200 · PEFT / LoRA",
              },
              {
                icon: Volume2,
                title: t("Speak"),
                tag: t("03 / SPEECH SYNTHESIS"),
                body: t(
                  "A natural neural voice brings the translation to life. Listen, adjust the pace, and take it with you.",
                ),
                tech: t("Edge TTS \u00B7 Neural voices"),
              },
            ].map((p, i) => (
              <button
                key={p.title}
                className={
                  "pipeline-card " + (pipelineInfo === i ? "selected" : "")
                }
                onClick={() => setPipelineInfo(i)}
              >
                <div className="pipeline-card-top">
                  <p.icon size={23} />
                  <span>0{i + 1}</span>
                </div>
                <div className="small-label">{p.tag}</div>
                <h3>{p.title}</h3>
                <p>{p.body}</p>
                <span className="tech-tag">{p.tech}</span>
              </button>
            ))}
          </div>
          <div className="pipeline-detail" aria-live="polite">
            <span className="tiny-dot" />
            {
              [
                "Audio input → language detection → editable transcription. Local processing uses Whisper; recordings are deleted after each request.",
                "Source text → NLLB tokenizer → LoRA-adapted transformer → translated text. Beam search balances fluency and meaning.",
                "Translated text → selected neural voice → MP3 output. Edge TTS sends the translated text to an external speech service.",
              ].map(t)[pipelineInfo]
            }
          </div>
        </section>
        <section id="research" className="research-section">
          <div>
            <div className="eyebrow">
              {t("BUILT ON RESEARCH. MEASURED IN PROGRESS.")}
            </div>
            <h2>
              {t("Small adaptation.")}
              <br />
              <span>{t("Meaningful improvement.")}</span>
            </h2>
            <p>
              {t(
                "A 600M-parameter multilingual foundation, adapted through low-rank fine-tuning across all twelve translation directions.",
              )}
            </p>
            <a
              className="text-link"
              href="https://huggingface.co/facebook/nllb-200-distilled-600M"
              target="_blank"
              rel="noreferrer"
            >
              {t("Explore the foundation model")}
              <ArrowRight size={15} />
            </a>
          </div>
          <div className="research-metrics">
            <div>
              <span>{t("VALIDATION BLEU")}</span>
              <strong>
                25.461 <small>+6.750</small>
              </strong>
              <p>{t("18.711 baseline \u2192 25.461 fine-tuned")}</p>
              <div className="compare-bar">
                <i />
                <b />
              </div>
            </div>
            <div>
              <span>{t("TEST BLEU")}</span>
              <strong>25.962</strong>
              <p>{t("Macro average \u00B7 1,800 examples")}</p>
            </div>
            <div>
              <span>{t("TEST chrF++")}</span>
              <strong>36.721</strong>
              <p>{t("12 directions \u00B7 150 examples each")}</p>
            </div>
          </div>
        </section>
      </main>
      <footer>
        <a className="brand" href="/">
          <AudioLines size={19} />
          PolyLingo<span className="brand-ai">AI</span>
        </a>
        <span>{t("Intelligent Multilingual Speech Translation Platform")}</span>
        <span>{t("Built for connection.")}</span>
      </footer>
      {showHistory && (
        <div className="drawer-backdrop" onClick={() => setShowHistory(false)}>
          <aside
            className="history-drawer"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="section-heading">
              <h2>{t("Your translations")}</h2>
              <button
                className="icon-button"
                aria-label={t("Close history")}
                onClick={() => setShowHistory(false)}
              >
                <X />
              </button>
            </div>
            <p className="muted">
              {t(
                "Stored only in this browser. Shared devices can access this history.",
              )}
            </p>
            <button
              className="secondary"
              onClick={() => {
                setHistory([]);
                localStorage.removeItem("polylingo-history");
              }}
            >
              <Trash2 size={14} />
              {t("Clear history")}
            </button>
            {!history.length && (
              <div className="empty">
                <History size={32} />
                <h3>{t("A world of words awaits.")}</h3>
                <p>{t("Your translations will appear here.")}</p>
              </div>
            )}
            {history.map((h) => (
              <article className="history-item" key={h.id}>
                <div className="history-meta">
                  {h.source.toUpperCase()} → {h.target.toUpperCase()}
                  <time>
                    {new Date(h.timestamp).toLocaleString(
                      locale === "ar" ? "ar-SA" : "en-GB",
                    )}
                  </time>
                </div>
                <p dir={languages.find((l) => l.iso === h.source)?.direction}>
                  {h.text}
                </p>
                {h.raw_transcript && (
                  <details className="history-transcript">
                    <summary>{t("View original transcript")}</summary>
                    <p
                      dir={languages.find((l) => l.iso === h.source)?.direction}
                    >
                      {h.raw_transcript}
                    </p>
                  </details>
                )}
                <strong
                  dir={languages.find((l) => l.iso === h.target)?.direction}
                >
                  {h.status === "error"
                    ? t("Translation failed. Repeat to retry.")
                    : h.translated_text}
                </strong>
                <div className="history-actions">
                  <button
                    className="text-link"
                    onClick={() => void copy(h.translated_text)}
                    disabled={!h.translated_text}
                  >
                    <Copy size={14} />
                    {t("Copy")}
                  </button>
                  <button
                    className="text-link"
                    disabled={!!manualStatus}
                    onClick={() => {
                      voiceWorkflow.cancel();
                      setTranscript(null);
                      setLastTranslatedInput("");
                      setText(h.text);
                      setSource(h.source);
                      setTarget(h.target);
                      setResult("");
                      changeAudio("");
                      setShowHistory(false);
                      document
                        .querySelector("#translator")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    <RotateCcw size={14} />
                    {t("Repeat")}
                  </button>
                  <button
                    className="text-link"
                    disabled={busy || !h.translated_text}
                    onClick={async () => {
                      setError("");
                      try {
                        const data = await synthesize({
                          text: h.translated_text,
                          language: h.target,
                          speed: 0,
                        });
                        changeAudio(data.url);
                        setTarget(h.target);
                        setResult(h.translated_text);
                        setShowHistory(false);
                        setTimeout(
                          () => void audioRef.current?.play().catch(() => {}),
                          50,
                        );
                      } catch (e) {
                        setShowHistory(false);
                        setError((e as Error).message);
                      }
                    }}
                  >
                    <Volume2 size={14} />
                    {t("Replay")}
                  </button>
                </div>
              </article>
            ))}
          </aside>
        </div>
      )}
    </div>
  );
}
