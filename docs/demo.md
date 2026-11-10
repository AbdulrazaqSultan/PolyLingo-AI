# Real application demo · عرض فعلي للمشروع

Captured on 2026-11-10 against the locally running React/Vite frontend and FastAPI backend. These are actual browser screenshots and frames, not generated mockups. The approximately 33-second animation retains the observed processing delays, including a roughly 17-second speech pipeline on this CPU run; this single observation is not a benchmark.

## What the recording demonstrates

1. Open the English homepage and voice workspace.
2. Feed neutral synthetic speech through Chrome's test microphone into the application's actual `getUserMedia` and `MediaRecorder` flow.
3. Automatically send exactly one interpreter request. Whisper tiny recognizes “Hello, how are you?”; the local NLLB + LoRA provider returns “مرحباً، كيف حالك؟”. Transcript refinement runs with the configured conservative behavior.
4. Load and play the actual returned Edge TTS audio, then inspect the browser-local history.
5. Switch to Arabic/RTL while preserving the input, translation, and selected languages.

The microphone fixture is synthetic, not a personal microphone recording. No inference endpoints or providers are mocked in this browser run. The MP4 soundtrack is assembled from that same input fixture and returned TTS file, aligned with the recorded actions; it is not a recording of system audio. GIF has no audio. No narration, faster playback, or replacement results were added.

## Assets

| File | Content |
| --- | --- |
| [interpreter-demo.gif](media/interpreter-demo.gif) | Embedded animated preview, approximately 1.06 MB |
| [interpreter-demo.mp4](media/interpreter-demo.mp4) | H.264/AAC video with synthetic input and actual translated speech, approximately 0.66 MB |
| [home-ar.png](media/home-ar.png), [home-en.png](media/home-en.png) | Full Arabic and English homepages |
| [translator-ar.png](media/translator-ar.png), [translator-en.png](media/translator-en.png) | Real voice result in both interface languages |
| [mobile-voice-ar.png](media/mobile-voice-ar.png) | Arabic voice workspace at a 390 px viewport |
| [admin-signin-ar.png](media/admin-signin-ar.png) | Protected administrator sign-in, without credentials |

Fresh browser contexts isolate the captures from personal browser data and existing history. Raw frames, speech fixtures, generated audio, and the detailed capture manifest stay in ignored `runtime/`; only the selected compressed presentation assets are committed.

## Verification

- 80 backend tests and 7 frontend tests passed; the production frontend build passed.
- The real browser speech run returned nonempty recognition, translation, and playable audio with one interpreter request, no browser runtime errors, and no failed API responses.
- History displayed the result; switching the UI language preserved source text and source/target language selections.
- Ten viewport checks passed: Arabic and English at 320, 390, 768, 1024, and 1440 px. Review caught a decorative glow extending outside narrow RTL viewports; its bounds and the decorative globe's overflow were corrected before final capture.
- All 21 original research artifact checksums remained unchanged.
- Both MP4 streams and all GIF frames were decoded after encoding to check file integrity.

This test uses an injected microphone fixture. Physical microphones, permission denial, all translation directions, and GPU performance still need separate device-specific acceptance checks. The admin capture does not demonstrate authenticated dashboard actions.

## Reproduce

Start the backend and frontend using the project setup instructions, with installed local model checkpoints and outbound access for Edge TTS. The capture uses an installed Google Chrome and optional development dependencies; no browser download is needed.

```powershell
cd frontend
npm ci
cd ..
python -m pip install av Pillow numpy edge-tts
python scripts/encode_demo.py --prepare-fixture
node scripts/check_layout.mjs
node scripts/capture_demo.mjs
python scripts/encode_demo.py
```

The default frontend URL is `http://127.0.0.1:5173`; set `DEMO_BASE_URL` to override it. Launch these commands from the repository root except for `npm ci`. Capture creates fresh contexts, grants microphone permission only to the test browser, and closes that browser afterward. Playback is muted during capture; the encoded MP4 includes the same audio files at their action timestamps.
