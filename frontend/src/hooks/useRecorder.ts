import { useRef, useState, useEffect } from "react";
export function useRecorder(
  onComplete: (blob: Blob) => void,
  onError: (message: string) => void,
  maxSeconds: number,
) {
  const [recording, setRecording] = useState(false),
    [seconds, setSeconds] = useState(0),
    [levels, setLevels] = useState<number[]>(Array(32).fill(0.1));
  const recorder = useRef<MediaRecorder | null>(null),
    stream = useRef<MediaStream | null>(null),
    context = useRef<AudioContext | null>(null),
    frame = useRef(0);
  const callback = useRef(onComplete);
  callback.current = onComplete;
  const stop = () => {
    if (recorder.current?.state === "recording") recorder.current.stop();
    stream.current?.getTracks().forEach((t) => t.stop());
    cancelAnimationFrame(frame.current);
    void context.current?.close();
    setRecording(false);
  };
  useEffect(() => {
    if (!recording) return;
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [recording]);
  useEffect(() => {
    if (recording && seconds >= maxSeconds) stop();
  }, [seconds, recording, maxSeconds]);
  useEffect(
    () => () => {
      stream.current?.getTracks().forEach((t) => t.stop());
      cancelAnimationFrame(frame.current);
      void context.current?.close();
    },
    [],
  );
  async function start() {
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
        throw new Error(
          "Microphone recording requires HTTPS or localhost and a supported browser.",
        );
      stream.current = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      const mime = ["audio/webm", "audio/mp4", "audio/ogg"].find((t) =>
        MediaRecorder.isTypeSupported(t),
      );
      const media = new MediaRecorder(
        stream.current,
        mime ? { mimeType: mime } : undefined,
      );
      recorder.current = media;
      const chunks: BlobPart[] = [];
      media.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      media.onstop = () =>
        callback.current(
          new Blob(chunks, { type: media.mimeType.split(";")[0] }),
        );
      context.current = new AudioContext();
      const analyser = context.current.createAnalyser();
      analyser.fftSize = 64;
      context.current.createMediaStreamSource(stream.current).connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const draw = () => {
        analyser.getByteFrequencyData(data);
        setLevels(Array.from(data, (x) => Math.max(0.08, x / 255)));
        frame.current = requestAnimationFrame(draw);
      };
      draw();
      setSeconds(0);
      setRecording(true);
      media.start(250);
    } catch (e) {
      stop();
      onError(
        e instanceof Error ? e.message : "Microphone permission was denied.",
      );
    }
  }
  return { recording, seconds, levels, start, stop };
}
