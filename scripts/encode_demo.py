"""Prepare neutral demo speech, or encode real browser frames without speeding them up.

Optional capture dependencies: pip install av Pillow numpy edge-tts
"""

import argparse
import asyncio
from bisect import bisect_right
from fractions import Fraction
import json
import math
from pathlib import Path

import av
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "runtime" / "capture"
MEDIA = ROOT / "docs" / "media"
RATE = 48000


def samples(path):
    chunks = []
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=RATE)
    with av.open(str(path)) as source:
        for frame in source.decode(audio=0):
            chunks.extend(item.to_ndarray()[0] for item in resampler.resample(frame))
        chunks.extend(item.to_ndarray()[0] for item in resampler.resample(None))
    return np.concatenate(chunks)


async def prepare_fixture():
    import edge_tts

    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    speech = runtime / "demo-source.mp3"
    await edge_tts.Communicate("Hello, how are you?", "en-US-AriaNeural").save(str(speech))
    signal = np.concatenate((np.zeros(RATE // 3), samples(speech), np.zeros(RATE * 4)))
    with av.open(str(runtime / "demo-microphone.wav"), "w") as output:
        stream = output.add_stream("pcm_s16le", rate=RATE)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray((signal * 32767).astype(np.int16)[None, :], format="s16", layout="mono")
        frame.sample_rate = RATE
        for packet in stream.encode(frame):
            output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    print("Prepared synthetic neutral microphone fixture in ignored runtime/.")


def encode():
    manifest = json.loads((WORK / "manifest.json").read_text(encoding="utf-8"))
    frames = manifest["frames"]
    times = [item["time_ms"] for item in frames]
    duration = times[-1] + 200
    markers = {item["name"]: item["time_ms"] for item in manifest["markers"]}
    MEDIA.mkdir(parents=True, exist_ok=True)

    # Use one palette across frames to avoid flicker; retain the original timing.
    selection = np.linspace(0, len(frames) - 1, min(24, len(frames)), dtype=int)
    sheet = Image.new("RGB", (252 * 6, 175 * 4))
    for pos, index in enumerate(selection):
        with Image.open(WORK / frames[index]["file"]) as source:
            sheet.paste(source.convert("RGB").resize((252, 175)), ((pos % 6) * 252, (pos // 6) * 175))
    palette = sheet.quantize(colors=128)
    gif_frames, durations = [], []
    for index, item in enumerate(frames):
        with Image.open(WORK / item["file"]) as source:
            gif_frames.append(source.convert("RGB").resize((1008, 700), Image.Resampling.LANCZOS).quantize(palette=palette, dither=Image.Dither.NONE))
        end = times[index + 1] if index + 1 < len(times) else duration
        durations.append(max(10, round(end / 10) * 10 - round(times[index] / 10) * 10))
    gif_frames[0].save(MEDIA / "interpreter-demo.gif", save_all=True, append_images=gif_frames[1:], duration=durations, loop=0, optimize=True, disposal=1)

    # The MP4 soundtrack uses the same synthetic input and actual returned TTS.
    sound = np.zeros(math.ceil(duration / 1000 * RATE), dtype=np.float32)
    for path, key, end_ms in [
        (ROOT / "runtime" / "demo-microphone.wav", "microphone_start", markers["microphone_stop"]),
        (WORK / "translated.mp3", "translated_audio_play", duration),
    ]:
        clip = samples(path)
        start = round(markers[key] / 1000 * RATE)
        count = min(len(clip), len(sound) - start, round((end_ms - markers[key]) / 1000 * RATE))
        sound[start:start + count] += clip[:count]

    fps = 15
    with av.open(str(MEDIA / "interpreter-demo.mp4"), "w", options={"movflags": "+faststart"}) as output:
        video = output.add_stream("libx264", rate=fps)
        video.width, video.height, video.pix_fmt = 1296, 900, "yuv420p"
        video.options = {"crf": "25", "preset": "medium"}
        audio = output.add_stream("aac", rate=RATE)
        audio.layout, audio.bit_rate = "mono", 64000
        audio_pos, last_index, picture = 0, -1, None
        for tick in range(math.ceil(duration / 1000 * fps)):
            index = max(0, bisect_right(times, tick * 1000 / fps) - 1)
            if index != last_index:
                with Image.open(WORK / frames[index]["file"]) as source:
                    picture = source.convert("RGB").resize((1296, 900), Image.Resampling.LANCZOS)
                last_index = index
            frame = av.VideoFrame.from_image(picture)
            frame.pts, frame.time_base = tick, Fraction(1, fps)
            for packet in video.encode(frame):
                output.mux(packet)
            while audio_pos < min(len(sound), (tick + 1) * RATE / fps):
                block = sound[audio_pos:audio_pos + 1024]
                frame = av.AudioFrame.from_ndarray(block[None, :], format="fltp", layout="mono")
                frame.sample_rate, frame.pts, frame.time_base = RATE, audio_pos, Fraction(1, RATE)
                for packet in audio.encode(frame):
                    output.mux(packet)
                audio_pos += len(block)
        for stream in (video, audio):
            for packet in stream.encode():
                output.mux(packet)
    print(json.dumps({"duration_seconds": duration / 1000, "source": manifest["source"], "translation": manifest["translated"], "files": {p.name: p.stat().st_size for p in MEDIA.glob("interpreter-demo.*")}}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-fixture", action="store_true")
    arguments = parser.parse_args()
    if arguments.prepare_fixture:
        asyncio.run(prepare_fixture())
    else:
        encode()
