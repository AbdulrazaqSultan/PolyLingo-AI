"""Small, context-gated ASR grammar rules; no full-sentence substitutions."""

import re
import unicodedata
from backend.app.ai.transcript_correction.base import (
    CorrectionCandidate,
    TranscriptCorrectionProvider,
)

# Each rule requires a grammatical neighbourhood rather than a free word replacement.
# Keeping the registry per language makes extension independent from the translator.
CONTEXT_RULES = {
    "ar": [
        (
            r"(?P<subject>هل\s+(?:أنت|انت|أنتم|انتم|أنتِ))\s+ب[حخ]ير(?=$|[\s؟?،,.!])",
            r"\g<subject> بخير",
        ),
    ],
    "en": [
        (
            r"\b(?P<question>how)\s+our\s+(?P<subject>you)\b",
            r"\g<question> are \g<subject>",
        )
    ],
    "fr": [
        (
            r"\b(?P<question>comment)\s+aller\s+(?P<subject>vous)\b",
            r"\g<question> allez-\g<subject>",
        )
    ],
    "zh": [],
}


class RuleBasedCorrectionProvider(TranscriptCorrectionProvider):
    async def correct(self, text, language, context="", asr_confidence=None):
        result = unicodedata.normalize("NFC", text)
        # Do not normalize Unicode compatibility characters, Arabic spelling variants,
        # casing, or repeated words: any of these can be intentional.
        result = re.sub(r"[ \t]+", " ", result).strip()
        for pattern, replacement in CONTEXT_RULES.get(language, []):
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        if language == "ar":
            pattern = r"^(?P<greeting>مرحب[اًًا]*|أهلاً|اهلا|السلام عليكم)[،,\s]+(?:كيف\s+)?(?P<state>حال[ء-ي]{1,2})\s+(?=هل\s+(?P<address>أنت|انت|أنتم|انتم))"

            def restore_question(match):
                state = match["state"]
                valid_forms = {
                    "حالك",
                    "حالكم",
                    "حالكن",
                    "حاله",
                    "حالها",
                    "حالنا",
                    "حالي",
                }
                if state not in valid_forms:
                    expected = (
                        "حالكم" if match["address"] in {"أنتم", "انتم"} else "حالك"
                    )
                    # A single corrupted suffix in a strongly constrained greeting /
                    # second-person question frame can be restored morphologically.
                    if (
                        len(state) != len(expected)
                        or sum(a != b for a, b in zip(state, expected)) != 1
                    ):
                        return match.group()
                    state = expected
                return f"{match['greeting']}، كيف {state}؟ "

            result = re.sub(pattern, restore_question, result)
            if re.search(r"هل (?:أنت|انت|أنتم|انتم|أنتِ) بخير$", result):
                result += "؟"
        # Punctuate only whole, unambiguous common question forms; leave clean prose alone.
        question = {
            "en": r"how are you",
            "fr": r"comment allez-vous",
            "ar": r"(?:كيف حال(?:ك|كم|ها|ه)|هل (?:أنت|انت|أنتم|انتم|أنتِ) بخير)",
        }.get(language)
        if question and re.fullmatch(question, result, re.IGNORECASE):
            if language in ("en", "fr"):
                result = result[0].upper() + result[1:]
            result += "؟" if language == "ar" else " ?" if language == "fr" else "?"
        return CorrectionCandidate(result, 0.99, True)
