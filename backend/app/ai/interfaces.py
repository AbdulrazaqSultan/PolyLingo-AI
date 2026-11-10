from abc import ABC, abstractmethod


class TranslationProvider(ABC):
    @abstractmethod
    def translate(self, text, source, target, beams=4) -> str:
        """Translate using provider-specific language metadata."""


class SpeechToTextProvider(ABC):
    @abstractmethod
    def transcribe(self, path, language=None) -> dict:
        """Return text and detected ISO language."""


class TextToSpeechProvider(ABC):
    @abstractmethod
    async def synthesize(self, text, language, voice=None, speed=0) -> bytes:
        """Return encoded audio."""
