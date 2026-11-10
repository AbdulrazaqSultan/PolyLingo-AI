from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass
class CorrectionCandidate:
    text: str
    confidence: float | None = None
    # Trusted local grammar providers supply a safety score, not calibrated confidence.
    trusted_rules: bool = False


class TranscriptCorrectionProvider(ABC):
    @abstractmethod
    async def correct(
        self,
        text: str,
        language: str,
        context: str = "",
        asr_confidence: float | None = None,
    ) -> CorrectionCandidate:
        """Return a same-language candidate; the service separately validates it."""


def changed_spans(raw: str, corrected: str) -> list[dict]:
    return [
        {"start": a, "end": b, "replacement": corrected[c:d]}
        for tag, a, b, c, d in SequenceMatcher(
            None, raw, corrected, autojunk=False
        ).get_opcodes()
        if tag != "equal"
    ]
