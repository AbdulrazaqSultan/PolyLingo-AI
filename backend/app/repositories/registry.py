from sqlalchemy import select
from backend.app.models.database_models import Record
from backend.app.schemas.api import Settings
from backend.app.core.config import config


def records(db, kind):
    return list(
        db.scalars(select(Record).where(Record.kind == kind).order_by(Record.id))
    )


def settings(db):
    rows = records(db, "settings")
    defaults = Settings(
        auto_translate_voice=config.auto_translate_voice,
        transcript_correction_enabled=config.transcript_correction_enabled,
        transcript_correction_provider=config.transcript_correction_provider,
        correction_confidence_threshold=config.correction_confidence_threshold,
    ).model_dump()
    return {**defaults, **(rows[0].data if rows else {})}


def seed(db):
    if records(db, "settings"):
        return
    for name, native, iso, nllb, tts, direction in [
        ("Arabic", "العربية", "ar", "arb_Arab", "ar-SA", "rtl"),
        ("English", "English", "en", "eng_Latn", "en-US", "ltr"),
        ("French", "Français", "fr", "fra_Latn", "fr-FR", "ltr"),
        ("Chinese", "中文", "zh", "zho_Hans", "zh-CN", "ltr"),
    ]:
        db.add(
            Record(
                kind="languages",
                data=dict(
                    name=name,
                    native=native,
                    iso=iso,
                    nllb=nllb,
                    stt=iso,
                    tts=tts,
                    direction=direction,
                    enabled=True,
                ),
            )
        )
    from backend.app.schemas.api import Model

    for name, typ, provider, mid in [
        (
            "PolyLingo NLLB + LoRA",
            "translation",
            "local_nllb",
            "facebook/nllb-200-distilled-600M",
        ),
        ("Whisper small", "stt", "whisper", "small"),
        ("Edge Neural Voices", "tts", "edge_tts", "edge"),
    ]:
        data = Model(
            name=name,
            model_type=typ,
            provider_type=provider,
            model_id=mid,
            adapter_path=config.adapter_path if typ == "translation" else "",
            languages=["ar", "en", "fr", "zh"],
            default=True,
            device="cpu" if typ == "stt" else "auto",
        ).model_dump()
        db.add(Record(kind="models", data=data))
    db.add(Record(kind="settings", data=settings(db)))
    db.commit()


def public_record(row):
    data = dict(row.data)
    data.pop("api_key", None)
    return {
        "id": row.id,
        **data,
        **(
            {"api_key_mask": "•••••••• (saved)" if row.secret else ""}
            if row.kind == "providers"
            else {}
        ),
    }
