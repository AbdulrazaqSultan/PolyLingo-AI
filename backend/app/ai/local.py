from pathlib import Path
from backend.app.ai.interfaces import (
    TranslationProvider,
    SpeechToTextProvider,
    TextToSpeechProvider,
)
from backend.app.core.config import config
from backend.app.core.errors import ServiceError


class LocalNLLBProvider(TranslationProvider):
    """Inference adapted from helper.py; database mappings replace research constants."""

    def __init__(self, spec):
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        from peft import PeftModel

        requested = spec["device"]
        if requested == "cuda" and not torch.cuda.is_available():
            raise ServiceError("CUDA was requested but is unavailable.")
        self.device = (
            "cuda" if requested != "cpu" and torch.cuda.is_available() else "cpu"
        )
        precision = spec.get("precision", "auto")
        dtype = (
            torch.float16
            if precision == "float16" or (precision == "auto" and self.device == "cuda")
            else torch.float32
        )
        adapter = Path(spec["adapter_path"])
        if not adapter.is_dir():
            raise ServiceError(
                "The trained adapter is unavailable. Check model configuration."
            )
        # Research tokenizer was saved by Transformers 5, where this field is a list.
        # Language token IDs remain in tokenizer.json; normalize only the runtime options.
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(adapter), extra_special_tokens={}
        )
        location = spec["local_path"] or spec["model_id"]
        if not spec["local_path"]:
            from huggingface_hub import snapshot_download
            from huggingface_hub.errors import LocalEntryNotFoundError

            try:
                location = snapshot_download(
                    spec["model_id"], cache_dir=config.hf_cache, local_files_only=True
                )
            except LocalEntryNotFoundError:
                pass
        base = AutoModelForSeq2SeqLM.from_pretrained(
            location,
            dtype=dtype,
            low_cpu_mem_usage=True,
            cache_dir=config.hf_cache,
            trust_remote_code=False,
        )
        self.model = (
            PeftModel.from_pretrained(base, str(adapter)).to(self.device).eval()
        )
        self.model.config.use_cache = True

    def translate(self, text, source, target, beams=4):
        import torch

        if (
            self.tokenizer.convert_tokens_to_ids(source["nllb"])
            == self.tokenizer.unk_token_id
        ):
            raise ServiceError(
                "The source language mapping is unsupported by this tokenizer.", 422
            )
        self.tokenizer.src_lang = source["nllb"]
        encoded = self.tokenizer(text, return_tensors="pt", truncation=False).to(
            self.device
        )
        if encoded.input_ids.shape[1] > 128:
            raise ServiceError(
                "This model accepts up to 128 source tokens. Split the text into shorter passages.",
                422,
            )
        bos = self.tokenizer.convert_tokens_to_ids(target["nllb"])
        if bos == self.tokenizer.unk_token_id:
            raise ServiceError(
                "The target language mapping is unsupported by this tokenizer.", 422
            )
        with torch.inference_mode():
            generated = self.model.generate(
                **encoded,
                forced_bos_token_id=bos,
                num_beams=beams,
                max_new_tokens=128,
                early_stopping=beams > 1,
                no_repeat_ngram_size=3,
            )
        return self.tokenizer.decode(generated[0], skip_special_tokens=True)


class WhisperProvider(SpeechToTextProvider):
    @staticmethod
    def checkpoint_directory(spec) -> Path:
        """Resolve a complete local checkpoint before evicting a working model."""
        from faster_whisper.utils import download_model
        from huggingface_hub.errors import LocalEntryNotFoundError

        try:
            directory = (
                Path(spec["local_path"])
                if spec["local_path"]
                else Path(
                    download_model(
                        spec["model_id"],
                        local_files_only=True,
                        cache_dir=config.whisper_cache or None,
                    )
                )
            )
            if not all(
                (directory / name).is_file()
                for name in ("model.bin", "config.json", "tokenizer.json")
            ):
                raise FileNotFoundError("Incomplete speech checkpoint")
            return directory
        except (LocalEntryNotFoundError, FileNotFoundError):
            raise ServiceError(
                "The speech recognition model is not installed. Ask the administrator to download the configured Whisper checkpoint."
            ) from None

    def __init__(self, spec):
        from faster_whisper import WhisperModel

        directory = self.checkpoint_directory(spec)
        device = "cpu" if spec["device"] == "auto" else spec["device"]
        self.model = WhisperModel(
            str(directory),
            device=device,
            compute_type="float16" if device == "cuda" else "int8",
            download_root=config.whisper_cache or None,
            local_files_only=True,
        )

    def transcribe(self, path, language=None):
        segments, info = self.model.transcribe(
            path, language=language, beam_size=4, vad_filter=True
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            raise ServiceError("No speech was detected. Try a clearer recording.", 422)
        return {"text": text, "language": info.language}


class EdgeTTSProvider(TextToSpeechProvider):
    async def synthesize(self, text, language, voice=None, speed=0):
        import edge_tts

        voices = await edge_tts.list_voices()
        options = [v["ShortName"] for v in voices if v["Locale"] == language["tts"]]
        if not options or (voice and voice not in options):
            raise ServiceError("No matching voice is available.", 422)
        stream = edge_tts.Communicate(text, voice or options[0], rate=f"{speed:+d}%")
        audio = bytearray()
        async for chunk in stream.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
        if not audio:
            raise ServiceError("Speech provider returned no audio.")
        return bytes(audio)
