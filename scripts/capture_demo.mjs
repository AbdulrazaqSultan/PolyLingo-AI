/**
 * Capture the real public UI in an isolated headless Chrome context.
 * The microphone is fed a synthetic neutral WAV; inference endpoints are never mocked.
 */
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { chromium } from "../frontend/node_modules/playwright-core/index.mjs";

const base = process.env.DEMO_BASE_URL || "http://127.0.0.1:5173";
const output = resolve("docs/media"),
  work = resolve("runtime/capture"),
  wave = resolve("runtime/demo-microphone.wav");
await mkdir(output, { recursive: true });
await mkdir(work, { recursive: true });
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: [
    "--use-fake-device-for-media-stream",
    "--use-file-for-fake-audio-capture=" + wave,
  ],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
  permissions: ["microphone"],
});
await context.addInitScript(() => {
  localStorage.setItem("polylingo-locale", "en");
});
const page = await context.newPage(),
  errors = [],
  failures = [],
  requests = [],
  markers = [],
  frames = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("response", (response) => {
  if (response.url().includes("/api/") && response.status() >= 400)
    failures.push({
      path: new URL(response.url()).pathname,
      status: response.status(),
    });
});
page.on("request", (request) => {
  if (request.url().includes("/api/speech/translate"))
    requests.push(request.method() + " " + new URL(request.url()).pathname);
});
let capturing = false,
  start = 0,
  loop;
const mark = (name) =>
  markers.push({ name, time_ms: Math.round(performance.now() - start) });
async function captureFrames() {
  while (capturing) {
    const before = performance.now(),
      file = "frame-" + String(frames.length).padStart(5, "0") + ".png";
    await page.screenshot({ path: resolve(work, file), type: "png" });
    frames.push({ file, time_ms: Math.round(before - start) });
    await new Promise((resolve) =>
      setTimeout(resolve, Math.max(0, 200 - (performance.now() - before))),
    );
  }
}
try {
  await page.goto(base, { waitUntil: "networkidle" });
  await page
    .locator(".language-bar select")
    .first()
    .locator("option")
    .last()
    .waitFor({ state: "attached" });
  assert.equal(await page.locator("html").getAttribute("lang"), "en");
  await page.screenshot({
    path: resolve(output, "home-en.png"),
    fullPage: true,
  });
  start = performance.now();
  capturing = true;
  loop = captureFrames();
  mark("overview_en");
  await page.waitForTimeout(1100);
  await page
    .getByRole("link", { name: "Start translating", exact: true })
    .click();
  await page.waitForTimeout(650);
  await page
    .locator(".tabs")
    .getByRole("button", { name: "Voice", exact: true })
    .click();
  await page.locator(".language-bar select").nth(0).selectOption("en");
  await page.locator(".language-bar select").nth(1).selectOption("ar");
  mark("voice_workspace");
  await page.waitForTimeout(700);
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await page.getByText("Listening…", { exact: true }).waitFor();
  mark("microphone_start");
  await page.waitForTimeout(4200);
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  mark("microphone_stop");
  await page
    .locator(".voice-ready")
    .waitFor({ state: "visible", timeout: 150000 });
  await page.locator(".audio-output audio").waitFor({ timeout: 15000 });
  mark("translation_ready");
  const source = await page
    .getByRole("textbox", { name: "Source text", exact: true })
    .inputValue();
  const translated = (
    await page.locator(".translation-output").innerText()
  ).trim();
  assert.ok(
    source.trim() && translated.trim(),
    "Real recognition and translation must produce text.",
  );
  assert.equal(
    requests.length,
    1,
    "A recording must send exactly one interpreter request.",
  );
  assert.equal(
    await page.locator(".error").count(),
    0,
    "The live pipeline must not display an error.",
  );
  await page
    .locator("#translator")
    .screenshot({ path: resolve(output, "translator-en.png") });
  const audio = await page.locator("audio").evaluate(async (audio) => {
    const response = await fetch(audio.src);
    return Array.from(new Uint8Array(await response.arrayBuffer()));
  });
  await writeFile(resolve(work, "translated.mp3"), Buffer.from(audio));
  await page.locator("audio").evaluate(async (audio) => {
    audio.muted = true;
    await audio.play();
  });
  mark("translated_audio_play");
  await page.waitForTimeout(2300);
  await page.locator("audio").evaluate((audio) => audio.pause());
  await page.getByRole("button", { name: /^History/ }).click();
  await page.locator(".history-item").waitFor();
  mark("history");
  assert.ok(
    (await page.locator(".history-item").innerText()).includes(translated),
  );
  await page.waitForTimeout(1000);
  await page
    .getByRole("button", { name: "Close history", exact: true })
    .click();
  await page.locator(".locale-switch button[lang=ar]").click();
  await page.waitForFunction(() => document.documentElement.dir === "rtl");
  mark("switch_to_arabic");
  await page.waitForTimeout(1200);
  assert.equal(
    await page.locator(".language-bar select").first().inputValue(),
    "en",
  );
  assert.equal(
    await page.locator(".language-bar select").last().inputValue(),
    "ar",
  );
  assert.equal(
    await page
      .getByRole("textbox", { name: "النص الأصلي", exact: true })
      .inputValue(),
    source,
  );
  await page
    .locator("#translator")
    .screenshot({ path: resolve(output, "translator-ar.png") });
  await page.getByRole("button", { name: /^السجل/ }).click();
  await page.locator(".history-item").waitFor();
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: "إغلاق السجل", exact: true }).click();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await page.waitForTimeout(1200);
  mark("overview_ar");
  await page.waitForTimeout(900);
  capturing = false;
  await loop;

  // Fresh contexts prevent history/credentials from entering documentation images.
  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
    isMobile: true,
    hasTouch: true,
  });
  const mobilePage = await mobile.newPage();
  await mobilePage.goto(base, { waitUntil: "networkidle" });
  await mobilePage
    .locator(".language-bar select option")
    .last()
    .waitFor({ state: "attached" });
  await mobilePage
    .locator(".tabs")
    .getByRole("button", { name: "صوت", exact: true })
    .click();
  assert.equal(
    await mobilePage.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
    true,
    "Mobile must not overflow horizontally.",
  );
  await mobilePage
    .locator("#translator")
    .screenshot({ path: resolve(output, "mobile-voice-ar.png") });
  await mobile.close();

  const ar = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    deviceScaleFactor: 1,
  });
  const arPage = await ar.newPage();
  await arPage.goto(base, { waitUntil: "networkidle" });
  await arPage.screenshot({
    path: resolve(output, "home-ar.png"),
    fullPage: true,
  });
  await arPage.goto(base + "/admin", { waitUntil: "networkidle" });
  await arPage
    .getByRole("heading", { name: "دخول المسؤول", exact: true })
    .waitFor();
  await arPage.screenshot({ path: resolve(output, "admin-signin-ar.png") });
  await ar.close();

  assert.deepEqual(errors, [], "No browser runtime errors are allowed.");
  assert.deepEqual(failures, [], "API errors must be fixed before publishing.");
  const manifest = {
    captured_at: new Date().toISOString(),
    viewport: { width: 1440, height: 1000 },
    duration_ms: frames.at(-1).time_ms + 200,
    frames,
    markers,
    source,
    translated,
    interpreter_requests: requests.length,
    console_errors: errors,
    api_failures: failures,
    microphone_fixture:
      "Synthetic neutral speech, not a personal microphone recording",
    checks: [
      "real microphone MediaRecorder with fixture",
      "one automatic interpreter request",
      "non-empty real ASR/translation",
      "real TTS loaded and played",
      "private history",
      "Arabic/English switch preserves input and languages",
      "mobile horizontal overflow",
      "protected admin sign-in",
    ],
  };
  await writeFile(
    resolve(work, "manifest.json"),
    JSON.stringify(manifest, null, 2),
  );
  console.log(
    JSON.stringify(
      {
        frames: frames.length,
        markers,
        source,
        translated,
        checks: manifest.checks,
      },
      null,
      2,
    ),
  );
} finally {
  capturing = false;
  if (loop) await loop.catch(() => {});
  await context.close();
  await browser.close();
}
