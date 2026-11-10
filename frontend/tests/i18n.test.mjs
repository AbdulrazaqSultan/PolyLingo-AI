import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { join, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Bundle TSX using the project's existing Vite/esbuild dependency; no browser or model download.
const directory = await mkdtemp(resolve("node_modules/.locale-test-"));
const output = join(directory, "components.mjs");
await build({
  stdin: {
    contents: `export {I18nProvider,LanguageSwitcher,translateMessage} from './src/i18n'; export {default as Translator} from './src/pages/Translator'; export {requestVoice} from './src/services/voice'; export {voiceReducer} from './src/hooks/useVoiceWorkflow';`,
    resolveDir: process.cwd(),
    loader: "tsx",
  },
  outfile: output,
  bundle: true,
  platform: "node",
  format: "esm",
  jsx: "automatic",
  packages: "external",
});
const {
  I18nProvider,
  Translator,
  translateMessage,
  requestVoice,
  voiceReducer,
} = await import(pathToFileURL(output));
const render = (locale) =>
  renderToStaticMarkup(
    React.createElement(
      I18nProvider,
      { initialLocale: locale },
      React.createElement(Translator),
    ),
  );

test("Arabic renders translator controls and selected interface language", () => {
  const html = render("ar");
  assert.ok(html.includes("ابدأ الترجمة"));
  assert.ok(html.includes("الترجمة من"));
  assert.ok(html.includes("مساحة الترجمة"));
  assert.match(html, /lang="ar" aria-pressed="true"/);
  assert.ok(!html.includes("Start translating"));
});
test("English renders the same workspace in English", () => {
  const html = render("en");
  assert.ok(html.includes("Start translating"));
  assert.ok(html.includes("TRANSLATE FROM"));
  assert.match(html, /lang="en" aria-pressed="true"/);
  assert.ok(!html.includes("ابدأ الترجمة"));
});
test("Speech failures have an Arabic translation and preserve English wording", () => {
  const message =
    "The speech recognition model is not installed. Ask the administrator to download the configured Whisper checkpoint.";
  assert.ok(translateMessage(message, "ar").includes("التعرف على الكلام"));
  assert.equal(translateMessage(message, "en"), message);
});
test("Unknown model names and Arabic/Chinese content are preserved", () => {
  for (const content of ["Custom model v2", "مرحبا بالعالم", "你好世界"])
    assert.equal(translateMessage(content, "ar"), content);
});
test("Voice state transitions ignore superseded requests and invalid stage jumps", () => {
  let state = voiceReducer(
    { phase: "idle", requestId: 0 },
    { type: "start", requestId: 1 },
  );
  assert.equal(state.phase, "uploading");
  assert.equal(
    voiceReducer(state, { type: "phase", requestId: 1, phase: "synthesizing" })
      .phase,
    "uploading",
  );
  for (const phase of [
    "transcribing",
    "correcting",
    "translating",
    "synthesizing",
    "complete",
  ])
    state = voiceReducer(state, { type: "phase", requestId: 1, phase });
  assert.equal(state.phase, "complete");
  state = voiceReducer(state, { type: "start", requestId: 2 });
  assert.deepEqual(
    voiceReducer(state, { type: "phase", requestId: 1, phase: "complete" }),
    state,
  );
  state = voiceReducer(state, { type: "cancel", requestId: 3 });
  assert.equal(state.phase, "idle");
  assert.deepEqual(
    voiceReducer(state, { type: "phase", requestId: 2, phase: "translating" }),
    state,
  );
});
test("Voice uses one streaming request and preserves detected language and raw Unicode text", async () => {
  const original = globalThis.fetch,
    calls = [],
    seen = [];
  const data = {
    detected_language: "ar",
    raw_transcript: "مرحباً حالب",
    corrected_transcript: "مرحباً، كيف حالك؟",
    translated_text: "Hello",
  };
  const events = [
    { event: "stage", stage: "transcribing" },
    { event: "stage", stage: "correcting" },
    { event: "transcript", data },
    { event: "stage", stage: "translating" },
    { event: "result", data },
  ];
  const bytes = new TextEncoder().encode(
    events.map((event) => JSON.stringify(event)).join("\n") + "\n",
  );
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(
      new ReadableStream({
        start(controller) {
          for (let i = 0; i < bytes.length; i += 5)
            controller.enqueue(bytes.slice(i, i + 5));
          controller.close();
        },
      }),
    );
  };
  const controller = new AbortController();
  try {
    await requestVoice(
      new Blob(["mock"], { type: "audio/wav" }),
      { source: null, target: "en", generate_voice: true, voice: "", speed: 0 },
      controller.signal,
      (event) => seen.push(event),
    );
  } finally {
    globalThis.fetch = original;
  }
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/speech/translate?stream=true");
  assert.equal(calls[0].options.body.has("source"), false);
  assert.equal(calls[0].options.body.get("target"), "en");
  assert.equal(calls[0].options.signal, controller.signal);
  assert.equal(
    seen.find((event) => event.event === "transcript").data.raw_transcript,
    data.raw_transcript,
  );
  assert.equal(seen.at(-1).data.detected_language, "ar");
});
test("Incomplete speech streams fail clearly instead of claiming success", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response('{"event":"stage","stage":"transcribing"}\n');
  try {
    await assert.rejects(
      requestVoice(
        new Blob(["mock"]),
        {
          source: "ar",
          target: "en",
          generate_voice: false,
          voice: "",
          speed: 0,
        },
        new AbortController().signal,
        () => {},
      ),
      /before completion/,
    );
  } finally {
    globalThis.fetch = original;
  }
});
assert.ok(directory.startsWith(resolve("node_modules") + sep));
await rm(directory, { recursive: true, force: true });
