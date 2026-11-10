from backend.app.ai.transcript_correction.base import TranscriptCorrectionProvider
from backend.app.ai.transcript_correction.rule_based import RuleBasedCorrectionProvider


class HybridCorrectionProvider(TranscriptCorrectionProvider):
    def __init__(self, advanced: TranscriptCorrectionProvider | None = None):
        self.normalizer = RuleBasedCorrectionProvider()
        self.advanced = advanced

    async def correct(self, text, language, context="", asr_confidence=None):
        normalized = await self.normalizer.correct(
            text, language, context, asr_confidence
        )
        if not self.advanced:
            return normalized
        return await self.advanced.correct(
            normalized.text, language, context, asr_confidence
        )
