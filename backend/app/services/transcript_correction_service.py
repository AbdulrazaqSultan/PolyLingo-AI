import asyncio
import re
import time
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from backend.app.ai.transcript_correction.base import changed_spans
from backend.app.ai.transcript_correction.rule_based import RuleBasedCorrectionProvider
from backend.app.ai.transcript_correction.llm_provider import LLMCorrectionProvider
from backend.app.ai.transcript_correction.hybrid import HybridCorrectionProvider
from backend.app.models.database_models import Record
from backend.app.repositories.registry import settings

# Protect exact sensitive substrings. No transcript or changed spans are written to server logs.
PROTECTED = re.compile(
    r'```[\s\S]*?```|`[^`\n]*`|"[^"\n]*"|https?://[^\s]+|www\.[^\s]+|[\w.+-]+@[\w.-]+\.[\w-]+|[A-Za-z]:\\[^\s]+|(?<!\w)/[\w./-]+|\b[A-Za-z]\w*(?:\+\+|#)(?!\w)|(?<!\w)\.[A-Za-z]\w+|(?<!\S)--?[\w-]+|\b\w*[_.:/@]\w+(?:[_.:/@-]\w+)*\b|\d+(?:[.,:/\-]\d+)*',
    re.UNICODE,
)
WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)


def protected_values(text):
    return Counter(PROTECTED.findall(text))


def script_ok(text, language):
    chars = [c for c in text if c.isalpha()]
    if not chars:
        return True
    if language == "ar":
        return sum("\u0600" <= c <= "\u06ff" for c in chars) / len(chars) >= 0.6
    if language == "zh":
        return sum("\u3400" <= c <= "\u9fff" for c in chars) / len(chars) >= 0.6
    return sum("LATIN" in unicodedata.name(c, "") for c in chars) / len(chars) >= 0.6


def validate_candidate(raw, candidate, language, normalized=None):
    if (
        not isinstance(candidate.text, str)
        or not candidate.text.strip()
        or len(candidate.text) > min(5000, max(30, len(raw) * 1.6))
    ):
        return None
    if protected_values(raw) != protected_values(candidate.text):
        return None
    if any(
        character in candidate.text and character not in raw for character in "`{}=<>"
    ):
        return None
    if not script_ok(candidate.text, language):
        return None
    # Code, quoted code, URLs and identifiers are safest left entirely unchanged.
    if re.search(
        r"[`{}=<>]|\b(?:def |class |const |SELECT |function )|\b[A-Za-z_]\w*\s*\(", raw
    ):
        return 1.0 if candidate.text == raw else None
    original_names = Counter(
        w for w in WORDS.findall(raw) if any(c.isupper() for c in w)
    )
    output_words = Counter(WORDS.findall(candidate.text))
    if any(output_words[word] < count for word, count in original_names.items()):
        return None
    letters = lambda text: "".join(c for c in text.casefold() if c.isalpha())
    if letters(raw) == letters(candidate.text):
        return 0.99
    ratio = SequenceMatcher(
        None, raw.casefold(), candidate.text.casefold(), autojunk=False
    ).ratio()
    if ratio < 0.68:
        return None
    if candidate.trusted_rules:
        return candidate.confidence
    if normalized is not None and WORDS.findall(normalized.casefold()) == WORDS.findall(
        candidate.text.casefold()
    ):
        return 0.99
    # There is no reliable confidence from a free-form LLM. Accept only minor edits
    # (or an explicit high-confidence deterministic lexical edit) and label this a safety score.
    raw_words = WORDS.findall(raw.casefold())
    new_words = WORDS.findall(candidate.text.casefold())
    matcher = SequenceMatcher(None, raw_words, new_words, autojunk=False)
    changed = [
        (raw_words[a:b], new_words[c:d])
        for op, a, b, c, d in matcher.get_opcodes()
        if op != "equal"
    ]
    if any(len(before) > 2 or len(after) > 3 for before, after in changed):
        return None
    if len(changed) > 2:
        return None
    # Outside the deterministic reference, only function-word edits are eligible.
    # Unknown substantive words, potential names and terminology are never rewritten.
    safe_function_words = {
        "ar": {"كيف", "هل", "أنت", "انت", "ما", "من", "في", "على", "إلى", "الى"},
        "en": {"how", "are", "our", "you", "is", "the", "a", "to", "in", "i", "it"},
        "fr": {"comment", "allez", "aller", "vous", "je", "tu", "est", "le", "la"},
        "zh": set(),
    }.get(language, set())
    for before, after in changed:
        if not before and any(word not in safe_function_words for word in after):
            return None
        # Punctuation/spacing-only changes are absent from word opcodes.
        if not set(before + after) <= safe_function_words:
            return None
    return min(0.99, 0.90 + 0.1 * ratio)


class TranscriptCorrectionService:
    def __init__(self, provider=None):
        self.override = provider

    async def correct(
        self, db, raw: str, language: str, context: str = "", asr_confidence=None
    ):
        start = time.perf_counter()
        opts = settings(db)
        response = {
            "raw_transcript": raw,
            "corrected_transcript": raw,
            "correction_applied": False,
            "correction_status": "unchanged",
            "correction_provider": opts["transcript_correction_provider"],
            "correction_confidence": None,
            "correction_safety_score": None,
            "changed_spans": [],
        }
        if (
            not raw.strip()
            or not opts["transcript_correction_enabled"]
            or language not in opts["correction_languages"]
        ):
            response["correction_status"] = "disabled"
        else:
            try:
                advanced = None
                provider_id = opts["correction_api_provider_id"]
                if provider_id is not None:
                    row = db.get(Record, provider_id)
                    if not row or row.kind != "providers" or not row.data["enabled"]:
                        raise ValueError("Unavailable correction provider.")
                    advanced = LLMCorrectionProvider(
                        row, opts["correction_model_id"], opts["correction_timeout"]
                    )
                kind = opts["transcript_correction_provider"]
                if self.override:
                    provider = self.override
                elif kind == "rule_based":
                    provider = RuleBasedCorrectionProvider()
                elif kind == "llm":
                    if advanced is None:
                        raise ValueError("No advanced correction provider configured.")
                    provider = advanced
                else:
                    provider = HybridCorrectionProvider(advanced)
                normalized = await RuleBasedCorrectionProvider().correct(raw, language)
                candidate = await asyncio.wait_for(
                    provider.correct(raw, language, context, asr_confidence),
                    opts["correction_timeout"],
                )
                score = validate_candidate(raw, candidate, language, normalized.text)
                if score is None or score < opts["correction_confidence_threshold"]:
                    response["correction_status"] = "fallback"
                else:
                    response.update(
                        corrected_transcript=candidate.text,
                        correction_applied=candidate.text != raw,
                        correction_status="corrected"
                        if candidate.text != raw
                        else "unchanged",
                        correction_safety_score=score,
                        changed_spans=changed_spans(raw, candidate.text),
                    )
            except Exception:
                response["correction_status"] = "fallback"
        response["correction_ms"] = round((time.perf_counter() - start) * 1000, 1)
        return response


correction_service = TranscriptCorrectionService()
