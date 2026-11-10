# Model, data, and evaluation

## Speech refinement responsibility

Whisper extracts raw speech. TranscriptCorrectionService performs conservative normalization and contextual ASR repair before translation, with optional OpenAI-compatible/custom correction APIs and exact raw fallback. The default Hybrid adds no model weights or GPU workload. Confidence thresholds use a documented guard score rather than claiming calibrated accuracy. Both transcripts are retained in the response and browser history. NLLB + LoRA exclusively translates the accepted transcript; it is never used as a spell checker. TTS generates target-language audio. See [transcript correction](transcript-correction.md) for limits and administration. Existing research metrics below are unchanged and do not evaluate the new correction stage.

The primary translation system is facebook/nllb-200-distilled-600M plus the trained LoRA adapter in models/polyligo_nllb_lora/best_adapter. The last_adapter is also retained. No retraining or merging into original weights occurs.

The adapter targets q_proj, k_proj, v_proj, and out_proj with rank 16, alpha 32, dropout 0.05, and SEQ_2_SEQ_LM task type. PEFT adds low-rank updates to frozen pretrained transformations. Source tokenizer language and forced target BOS implement the direction choice.

Research configuration: 128-token source/target, beam search 4, max generated tokens 128, no-repeat trigram constraint, two epochs, learning rate 1e-4, label smoothing 0.10, gradient accumulation 4, batch size 4, temperature sampling alpha 0.7. The inference service preserves the generation approach while rejecting excessive input rather than truncating it.

Mappings: Arabic arb_Arab, English eng_Latn, French fra_Latn, Chinese zho_Hans. These are seeded from the helper's mappings and configurable through the registry.

The notebook combines aligned OPUS100 multilingual rows from nirmalendu01/opus100-en-fr-de-ar-zh with Helsinki-NLP/opus-100 bilingual anchors. English anchor holdouts prevent overlap across aligned holdout sets. See helper.py for cleaning, script checks, balancing, sampling, and direction evaluation.

## Verified evaluation

| Metric | Baseline validation | Fine-tuned validation | Final test |
|---|---:|---:|---:|
| BLEU | 18.711 | 25.461 | 25.962 |
| chrF++ | 34.074 | 36.742 | 36.721 |

CSV evidence: results/baseline_validation_metrics.csv, finetuned_validation_metrics.csv, before_after_comparison.csv, final_test_metrics.csv. Each evaluation has 150 examples across each of 12 directions. Validation BLEU gain is +6.750. Supplied best validation loss 3.0535 and epoch 2 are consistent with the requested research report; notebook output is the evidence for training selection, separate from evaluation CSVs. No extra quality metrics are fabricated.

Mean gains do not imply improvements in every direction. English → Chinese validation BLEU and chrF++ decline slightly, and Arabic → Chinese chrF++ declines. Use the direction table to assess intended use.

## Model terms

The [upstream model card](https://huggingface.co/facebook/nllb-200-distilled-600M) specifies CC-BY-NC-4.0, a research focus, and production deployment outside intended use. Application engineering does not remove those restrictions or establish suitability for medical/legal/high-stakes translation.

