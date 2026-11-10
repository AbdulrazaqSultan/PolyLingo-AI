"""
PolyLingo AI helper module
==========================

Clean utilities for:
- reproducibility
- multilingual parallel-data cleaning/building
- NLLB tokenization
- LoRA fine-tuning
- BLEU / chrF evaluation
- translation inference

The notebook stays readable while the reusable logic lives here.
"""

from __future__ import annotations

import gc
import math
import random
import re
import time
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, WeightedRandomSampler

from datasets import Dataset, concatenate_datasets
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    get_cosine_schedule_with_warmup,
)

from peft import LoraConfig, TaskType, get_peft_model, PeftModel

import sacrebleu

# ---------------------------------------------------------------------------
# Language definitions
# ---------------------------------------------------------------------------

LANGUAGES: Dict[str, Dict[str, str]] = {
    "ar": {
        "name": "Arabic",
        "native": "العربية",
        "nllb": "arb_Arab",
    },
    "en": {
        "name": "English",
        "native": "English",
        "nllb": "eng_Latn",
    },
    "fr": {
        "name": "French",
        "native": "Français",
        "nllb": "fra_Latn",
    },
    "zh": {
        "name": "Chinese",
        "native": "中文",
        "nllb": "zho_Hans",
    },
}

LANG_ORDER = ["ar", "en", "fr", "zh"]
ALL_DIRECTIONS = [
    f"{src}->{tgt}"
    for src in LANG_ORDER
    for tgt in LANG_ORDER
    if src != tgt
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ProjectConfig:
    seed: int = 42

    model_name: str = "facebook/nllb-200-distilled-600M"

    # Dataset sizing: balanced across all 12 directions.
    train_per_direction: int = 5000
    eval_per_direction: int = 150
    anchor_examples_per_pair: int = 12000

    # Sequence lengths are intentionally conservative for an 8 GB GPU.
    max_source_length: int = 128
    max_target_length: int = 128

    # LoRA
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_targets: Tuple[str, ...] = (
        "q_proj",
        "k_proj",
        "v_proj",
        "out_proj",
    )

    # Optimization
    learning_rate: float = 1e-4
    weight_decay: float = 0.01
    label_smoothing: float = 0.10
    train_batch_size: int = 4
    eval_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    epochs: int = 2
    warmup_ratio: float = 0.05
    max_grad_norm: float = 1.0

    # Evaluation / generation
    num_beams: int = 4
    generation_max_new_tokens: int = 128

    # Early stopping uses validation loss because generation over all
    # directions every epoch is expensive. Final selection is verified
    # with BLEU/chrF after training.
    early_stopping_patience: int = 2
    min_delta: float = 1e-4

    # Reweight multilingual sampling using temperature smoothing.
    # alpha < 1 increases exposure of lower-resource directions.
    sampling_alpha: float = 0.7

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Reproducibility / environment
# ---------------------------------------------------------------------------

def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    try:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except Exception:
        pass


def get_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def print_environment() -> None:
    device = get_device()
    print("PyTorch :", torch.__version__)
    print("Device  :", device)
    print("CUDA    :", torch.version.cuda)

    if device.type == "cuda":
        props = torch.cuda.get_device_properties(0)
        print("GPU     :", torch.cuda.get_device_name(0))
        print("VRAM GB :", round(props.total_memory / 1024 ** 3, 2))


# ---------------------------------------------------------------------------
# Text normalization / data-quality filters
# ---------------------------------------------------------------------------

_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_SPACE_RE = re.compile(r"\s+")
_ONLY_PUNCT_RE = re.compile(r"^[\W_]+$", flags=re.UNICODE)
_REPEAT_RE = re.compile(r"(.)\1{8,}", flags=re.UNICODE)


def normalize_text(text: object) -> str:
    if text is None:
        return ""

    text = str(text)
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def _arabic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    ar = sum(
        1
        for c in letters
        if "\u0600" <= c <= "\u06FF"
        or "\u0750" <= c <= "\u077F"
        or "\u08A0" <= c <= "\u08FF"
    )
    return ar / len(letters)


def _cjk_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    zh = sum(
        1
        for c in chars
        if "\u4E00" <= c <= "\u9FFF"
        or "\u3400" <= c <= "\u4DBF"
    )
    return zh / len(chars)


def language_script_ok(text: str, lang: str) -> bool:
    """
    Conservative script checks only where script is strongly informative.

    English and French share Latin script, so we deliberately do not pretend
    script detection can distinguish them.
    """
    if lang == "ar":
        return _arabic_ratio(text) >= 0.35
    if lang == "zh":
        return _cjk_ratio(text) >= 0.20
    return True


def pair_quality_ok(
        source: str,
        target: str,
        src_lang: str,
        tgt_lang: str,
        min_chars: int = 4,
        max_chars: int = 600,
        max_length_ratio: float = 4.5,
) -> bool:
    source = normalize_text(source)
    target = normalize_text(target)

    if not source or not target:
        return False

    if len(source) < min_chars or len(target) < min_chars:
        return False

    if len(source) > max_chars or len(target) > max_chars:
        return False

    if _ONLY_PUNCT_RE.match(source) or _ONLY_PUNCT_RE.match(target):
        return False

    if _REPEAT_RE.search(source) or _REPEAT_RE.search(target):
        return False

    if source.casefold() == target.casefold() and src_lang != tgt_lang:
        return False

    ratio = max(len(source), len(target)) / max(1, min(len(source), len(target)))
    if ratio > max_length_ratio:
        return False

    if not language_script_ok(source, src_lang):
        return False

    if not language_script_ok(target, tgt_lang):
        return False

    return True


def clean_parallel_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    required = {"source", "target", "src_lang", "tgt_lang"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    cleaned = df.copy()
    cleaned["source"] = cleaned["source"].map(normalize_text)
    cleaned["target"] = cleaned["target"].map(normalize_text)

    keep = [
        pair_quality_ok(src, tgt, sl, tl)
        for src, tgt, sl, tl in cleaned[
            ["source", "target", "src_lang", "tgt_lang"]
        ].itertuples(index=False, name=None)
    ]

    cleaned = cleaned.loc[keep].copy()
    cleaned["pair"] = cleaned["src_lang"] + "->" + cleaned["tgt_lang"]

    # Exact directed duplicates are removed to reduce memorization.
    cleaned = cleaned.drop_duplicates(
        subset=["source", "target", "src_lang", "tgt_lang"]
    ).reset_index(drop=True)

    return cleaned


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------

def explode_aligned_rows(
        df: pd.DataFrame,
        languages: Sequence[str] = LANG_ORDER,
) -> pd.DataFrame:
    rows: List[Dict[str, str]] = []

    for row in df.to_dict("records"):
        for src_lang in languages:
            for tgt_lang in languages:
                if src_lang == tgt_lang:
                    continue

                rows.append(
                    {
                        "source": row[src_lang],
                        "target": row[tgt_lang],
                        "src_lang": src_lang,
                        "tgt_lang": tgt_lang,
                        "pair": f"{src_lang}->{tgt_lang}",
                        "origin": "bridge",
                    }
                )

    return clean_parallel_dataframe(pd.DataFrame(rows))


def split_aligned_by_anchor(
        aligned_df: pd.DataFrame,
        seed: int = 42,
        train_ratio: float = 0.80,
        val_ratio: float = 0.10,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split BEFORE exploding directions. This prevents the same semantic sentence
    from appearing in train in one direction and evaluation in another.
    """
    rng = np.random.default_rng(seed)
    indices = np.arange(len(aligned_df))
    rng.shuffle(indices)

    n = len(indices)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    train_idx = indices[:n_train]
    val_idx = indices[n_train:n_train + n_val]
    test_idx = indices[n_train + n_val:]

    return (
        aligned_df.iloc[train_idx].reset_index(drop=True),
        aligned_df.iloc[val_idx].reset_index(drop=True),
        aligned_df.iloc[test_idx].reset_index(drop=True),
    )


def aligned_holdout_english_anchors(
        val_aligned: pd.DataFrame,
        test_aligned: pd.DataFrame,
) -> set:
    values = pd.concat(
        [val_aligned["en"], test_aligned["en"]],
        ignore_index=True,
    )
    return {normalize_text(x).casefold() for x in values}


def opus_pair_to_dataframe(
        hf_dataset,
        lang_a: str,
        lang_b: str,
        holdout_english: Optional[set] = None,
        bidirectional: bool = True,
) -> pd.DataFrame:
    rows = []

    for item in hf_dataset:
        tr = item["translation"]
        a = normalize_text(tr.get(lang_a, ""))
        b = normalize_text(tr.get(lang_b, ""))

        if holdout_english:
            en_text = a if lang_a == "en" else b if lang_b == "en" else None
            if en_text and en_text.casefold() in holdout_english:
                continue

        rows.append(
            {
                "source": a,
                "target": b,
                "src_lang": lang_a,
                "tgt_lang": lang_b,
                "pair": f"{lang_a}->{lang_b}",
                "origin": "opus100",
            }
        )

        if bidirectional:
            rows.append(
                {
                    "source": b,
                    "target": a,
                    "src_lang": lang_b,
                    "tgt_lang": lang_a,
                    "pair": f"{lang_b}->{lang_a}",
                    "origin": "opus100",
                }
            )

    return clean_parallel_dataframe(pd.DataFrame(rows))


def balanced_direction_sample(
        df: pd.DataFrame,
        per_direction: int,
        seed: int = 42,
) -> pd.DataFrame:
    parts = []

    for pair in ALL_DIRECTIONS:
        group = df[df["pair"] == pair]
        if group.empty:
            continue

        n = min(per_direction, len(group))
        parts.append(group.sample(n=n, random_state=seed))

    if not parts:
        raise ValueError("No language directions were available after cleaning.")

    out = pd.concat(parts, ignore_index=True)
    out = out.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return out


def stratified_eval_sample(
        df: pd.DataFrame,
        per_direction: int,
        seed: int = 42,
) -> pd.DataFrame:
    return balanced_direction_sample(df, per_direction, seed)


def direction_table(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df["pair"]
        .value_counts()
        .rename_axis("direction")
        .reset_index(name="examples")
        .sort_values("direction")
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# NLLB tokenization
# ---------------------------------------------------------------------------

def _tokenize_one_direction(
        pair_df: pd.DataFrame,
        tokenizer,
        max_source_length: int,
        max_target_length: int,
) -> Dataset:
    if pair_df.empty:
        raise ValueError("pair_df is empty.")

    src_lang = pair_df["src_lang"].iloc[0]
    tgt_lang = pair_df["tgt_lang"].iloc[0]

    tokenizer.src_lang = LANGUAGES[src_lang]["nllb"]
    tokenizer.tgt_lang = LANGUAGES[tgt_lang]["nllb"]

    ds = Dataset.from_pandas(
        pair_df[
            ["source", "target", "src_lang", "tgt_lang", "pair"]
        ],
        preserve_index=False,
    )

    def encode(batch):
        model_inputs = tokenizer(
            batch["source"],
            text_target=batch["target"],
            max_length=max_source_length,
            max_target_length=max_target_length,
            truncation=True,
        )
        return model_inputs

    tokenized = ds.map(
        encode,
        batched=True,
        remove_columns=["source", "target"],
        desc=f"Tokenizing {src_lang}->{tgt_lang}",
    )
    return tokenized


def tokenize_multilingual_dataframe(
        df: pd.DataFrame,
        tokenizer,
        max_source_length: int,
        max_target_length: int,
) -> Dataset:
    pieces = []

    for pair in sorted(df["pair"].unique()):
        part = df[df["pair"] == pair].reset_index(drop=True)
        pieces.append(
            _tokenize_one_direction(
                part,
                tokenizer,
                max_source_length,
                max_target_length,
            )
        )

    return concatenate_datasets(pieces).shuffle(seed=42)


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def temperature_sampling_weights(
        pairs: Sequence[str],
        alpha: float = 0.7,
) -> torch.DoubleTensor:
    """
    Example-level weights that produce direction probabilities proportional
    to n_direction ** alpha.

    alpha=1.0 -> natural data distribution
    alpha<1.0 -> smoother / more exposure for smaller directions
    """
    pair_series = pd.Series(list(pairs))
    counts = pair_series.value_counts().to_dict()

    weights = [
        counts[pair] ** (alpha - 1.0)
        for pair in pair_series
    ]
    return torch.as_tensor(weights, dtype=torch.double)


# ---------------------------------------------------------------------------
# LoRA model
# ---------------------------------------------------------------------------

def build_lora_nllb(config: ProjectConfig):
    tokenizer = AutoTokenizer.from_pretrained(config.model_name)

    dtype = torch.float16 if torch.cuda.is_available() else torch.float32

    model = AutoModelForSeq2SeqLM.from_pretrained(
        config.model_name,
        dtype=dtype,
        low_cpu_mem_usage=True,
    )

    # Gradient checkpointing trades compute for memory, useful on 8 GB VRAM.
    model.gradient_checkpointing_enable()
    model.config.use_cache = False

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        inference_mode=False,
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=list(config.lora_targets),
        bias="none",
    )

    model = get_peft_model(model, lora_config)
    return tokenizer, model


def print_trainable_parameters(model) -> Dict[str, float]:
    trainable = 0
    total = 0

    for p in model.parameters():
        total += p.numel()
        if p.requires_grad:
            trainable += p.numel()

    ratio = 100 * trainable / max(1, total)

    print(f"Trainable parameters : {trainable:,}")
    print(f"Total parameters     : {total:,}")
    print(f"Trainable %          : {ratio:.4f}%")

    return {
        "trainable": trainable,
        "total": total,
        "trainable_percent": ratio,
    }


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

class TranslationTrainer:
    """Training loop for LoRA-based NLLB fine-tuning.

    Design goals:
    - keep string metadata out of the tensor collator,
    - use AMP safely on CUDA,
    - preserve an effective batch size via gradient accumulation,
    - keep gradient checkpointing compatible with training,
    - validate with the same autocast policy as training,
    - save the best adapter based on finite validation loss.
    """

    def __init__(
        self,
        model,
        tokenizer,
        config: ProjectConfig,
        output_dir: Path,
        device: Optional[torch.device] = None,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.device = device or get_device()
        self.model.to(self.device)

        # NLLB generation cache is useful for inference, but it is incompatible
        # with gradient checkpointing during training.
        self.model.config.use_cache = False

        self.optimizer = torch.optim.AdamW(
            [p for p in self.model.parameters() if p.requires_grad],
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )

        self.loss_fn = nn.CrossEntropyLoss(
            ignore_index=-100,
            label_smoothing=config.label_smoothing,
        )

        self.history = {
            "train_loss": [],
            "val_loss": [],
            "lr": [],
        }

        self.best_val_loss = math.inf
        self.best_epoch = -1
        self.no_improve_epochs = 0

    def _build_loaders(self, train_ds: Dataset, val_ds: Dataset):
        collator = DataCollatorForSeq2Seq(
            tokenizer=self.tokenizer,
            model=self.model,
            padding="longest",
            label_pad_token_id=-100,
            return_tensors="pt",
        )

        # Keep the pair labels only long enough to compute multilingual
        # sampling weights. They must not reach the tokenizer collator.
        train_pairs = train_ds["pair"]
        weights = temperature_sampling_weights(
            train_pairs,
            alpha=self.config.sampling_alpha,
        )

        sampler = WeightedRandomSampler(
            weights=weights,
            num_samples=len(weights),
            replacement=True,
        )

        model_columns = {
            "input_ids",
            "attention_mask",
            "labels",
        }

        train_remove_columns = [
            column
            for column in train_ds.column_names
            if column not in model_columns
        ]
        val_remove_columns = [
            column
            for column in val_ds.column_names
            if column not in model_columns
        ]

        train_model_ds = train_ds.remove_columns(train_remove_columns)
        val_model_ds = val_ds.remove_columns(val_remove_columns)

        print(
            "Training columns passed to model:",
            train_model_ds.column_names,
        )
        print(
            "Validation columns passed to model:",
            val_model_ds.column_names,
        )

        train_loader = DataLoader(
            train_model_ds,
            batch_size=self.config.train_batch_size,
            sampler=sampler,
            collate_fn=collator,
            num_workers=0,
            pin_memory=(self.device.type == "cuda"),
        )

        val_loader = DataLoader(
            val_model_ds,
            batch_size=self.config.eval_batch_size,
            shuffle=False,
            collate_fn=collator,
            num_workers=0,
            pin_memory=(self.device.type == "cuda"),
        )

        return train_loader, val_loader

    def _compute_loss(self, batch) -> torch.Tensor:
        labels = batch["labels"]

        # Passing labels lets the seq2seq model create decoder inputs by
        # shifting the targets internally. We intentionally compute our own
        # CrossEntropyLoss so label smoothing is explicit and reproducible.
        outputs = self.model(
            input_ids=batch["input_ids"],
            attention_mask=batch["attention_mask"],
            labels=labels,
            use_cache=False,
        )

        logits = outputs.logits

        # This operation is executed inside torch.autocast in both training
        # and validation. PyTorch AMP chooses the numerically appropriate
        # precision for CrossEntropyLoss.
        return self.loss_fn(
            logits.reshape(-1, logits.size(-1)),
            labels.reshape(-1),
        )

    @torch.no_grad()
    def _validate_loss(self, loader) -> float:
        self.model.eval()

        running_loss = 0.0
        examples = 0
        use_amp = self.device.type == "cuda"

        for batch in loader:
            batch = {
                key: value.to(self.device, non_blocking=True)
                for key, value in batch.items()
            }

            # Validation uses the same AMP policy as training. The old file
            # had a second _validate_loss definition without autocast; because
            # Python kept the second definition, it could produce FP16 inf.
            with torch.autocast(
                device_type=self.device.type,
                dtype=torch.float16,
                enabled=use_amp,
            ):
                loss = self._compute_loss(batch)

            if not torch.isfinite(loss):
                raise FloatingPointError(
                    "Non-finite validation loss detected. "
                    f"Current value: {loss.item()}"
                )

            batch_size = batch["input_ids"].size(0)
            running_loss += loss.detach().float().item() * batch_size
            examples += batch_size

        if examples == 0:
            raise ValueError("Validation loader is empty.")

        return running_loss / examples

    def fit(self, train_ds: Dataset, val_ds: Dataset):
        train_loader, val_loader = self._build_loaders(train_ds, val_ds)

        total_update_steps_per_epoch = math.ceil(
            len(train_loader)
            / self.config.gradient_accumulation_steps
        )
        total_training_steps = (
            total_update_steps_per_epoch * self.config.epochs
        )
        warmup_steps = int(
            total_training_steps * self.config.warmup_ratio
        )

        scheduler = get_cosine_schedule_with_warmup(
            self.optimizer,
            num_warmup_steps=warmup_steps,
            num_training_steps=total_training_steps,
        )

        use_amp = self.device.type == "cuda"

        # Current PyTorch AMP API. This replaces the deprecated
        # torch.cuda.amp.GradScaler(...).
        scaler = torch.amp.GradScaler(
            "cuda",
            enabled=use_amp,
        )

        effective_batch_size = (
            self.config.train_batch_size
            * self.config.gradient_accumulation_steps
        )

        print(f"Device               : {self.device}")
        print(f"Train batches/epoch  : {len(train_loader)}")
        print(f"Train batch size     : {self.config.train_batch_size}")
        print(
            "Gradient accumulation:",
            self.config.gradient_accumulation_steps,
        )
        print(f"Effective batch size : {effective_batch_size}")
        print(f"Optimizer steps/epoch: {total_update_steps_per_epoch}")

        started = time.perf_counter()

        for epoch in range(1, self.config.epochs + 1):
            self.model.train()
            self.model.config.use_cache = False
            self.optimizer.zero_grad(set_to_none=True)

            running_loss = 0.0
            examples = 0

            for step, batch in enumerate(train_loader, start=1):
                batch = {
                    key: value.to(self.device, non_blocking=True)
                    for key, value in batch.items()
                }

                with torch.autocast(
                    device_type=self.device.type,
                    dtype=torch.float16,
                    enabled=use_amp,
                ):
                    loss = self._compute_loss(batch)
                    scaled_loss = (
                        loss
                        / self.config.gradient_accumulation_steps
                    )

                if not torch.isfinite(loss):
                    raise FloatingPointError(
                        "Non-finite training loss detected. "
                        f"Epoch={epoch}, step={step}, value={loss.item()}"
                    )

                scaler.scale(scaled_loss).backward()

                do_update = (
                    step % self.config.gradient_accumulation_steps == 0
                    or step == len(train_loader)
                )

                if do_update:
                    scaler.unscale_(self.optimizer)
                    torch.nn.utils.clip_grad_norm_(
                        self.model.parameters(),
                        self.config.max_grad_norm,
                    )

                    scaler.step(self.optimizer)
                    scaler.update()
                    self.optimizer.zero_grad(set_to_none=True)
                    scheduler.step()

                batch_size = batch["input_ids"].size(0)
                running_loss += loss.detach().float().item() * batch_size
                examples += batch_size

                if step % 250 == 0 or step == len(train_loader):
                    current_loss = running_loss / max(1, examples)
                    print(
                        f"Epoch {epoch}/{self.config.epochs} | "
                        f"batch {step}/{len(train_loader)} | "
                        f"train_loss={current_loss:.4f}"
                    )

            train_loss = running_loss / max(1, examples)
            val_loss = self._validate_loss(val_loader)
            lr = self.optimizer.param_groups[0]["lr"]

            self.history["train_loss"].append(train_loss)
            self.history["val_loss"].append(val_loss)
            self.history["lr"].append(lr)

            print(
                f"\nEpoch {epoch}/{self.config.epochs} completed | "
                f"train_loss={train_loss:.4f} | "
                f"val_loss={val_loss:.4f} | "
                f"lr={lr:.2e}"
            )

            # Save a recoverable adapter after every completed epoch.
            last_adapter_dir = self.output_dir / "last_adapter"
            self.model.save_pretrained(last_adapter_dir)
            self.tokenizer.save_pretrained(last_adapter_dir)

            improved = (
                val_loss
                < self.best_val_loss - self.config.min_delta
            )

            if improved:
                self.best_val_loss = val_loss
                self.best_epoch = epoch
                self.no_improve_epochs = 0

                best_adapter_dir = self.output_dir / "best_adapter"
                self.model.save_pretrained(best_adapter_dir)
                self.tokenizer.save_pretrained(best_adapter_dir)
                print("Saved new best adapter.")
            else:
                self.no_improve_epochs += 1

            if (
                self.no_improve_epochs
                >= self.config.early_stopping_patience
            ):
                print("Early stopping triggered.")
                break

        elapsed = time.perf_counter() - started
        print(f"Training seconds: {elapsed:.1f}")
        print(f"Best epoch      : {self.best_epoch}")
        print(f"Best val loss   : {self.best_val_loss:.4f}")

        return self.history


# ---------------------------------------------------------------------------
# Translation / evaluation
# ---------------------------------------------------------------------------

class NLLBTranslator:
    def __init__(
            self,
            model,
            tokenizer,
            device: Optional[torch.device] = None,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device or get_device()

        self.model.to(self.device)
        self.model.eval()
        self.model.config.use_cache = True

    @torch.no_grad()
    def translate(
            self,
            texts: Sequence[str] | str,
            src_lang: str,
            tgt_lang: str,
            num_beams: int = 4,
            max_new_tokens: int = 128,
            batch_size: int = 8,
    ) -> List[str] | str:
        single = isinstance(texts, str)
        if single:
            texts = [texts]

        src_code = LANGUAGES[src_lang]["nllb"]
        tgt_code = LANGUAGES[tgt_lang]["nllb"]

        self.tokenizer.src_lang = src_code

        outputs: List[str] = []

        for start in range(0, len(texts), batch_size):
            batch_texts = list(texts[start:start + batch_size])

            encoded = self.tokenizer(
                batch_texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=128,
            ).to(self.device)

            generated = self.model.generate(
                **encoded,
                forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(
                    tgt_code
                ),
                num_beams=num_beams,
                max_new_tokens=max_new_tokens,
                early_stopping=True,
                no_repeat_ngram_size=3,
            )

            outputs.extend(
                self.tokenizer.batch_decode(
                    generated,
                    skip_special_tokens=True,
                )
            )

        return outputs[0] if single else outputs


def _bleu_tokenizer_for_target(tgt_lang: str) -> str:
    return "zh" if tgt_lang == "zh" else "13a"


def evaluate_translation_dataframe(
        translator: NLLBTranslator,
        eval_df: pd.DataFrame,
        num_beams: int = 4,
        max_new_tokens: int = 128,
        batch_size: int = 8,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    predictions = []

    for pair in sorted(eval_df["pair"].unique()):
        part = eval_df[eval_df["pair"] == pair].reset_index(drop=True)

        src_lang = part["src_lang"].iloc[0]
        tgt_lang = part["tgt_lang"].iloc[0]

        preds = translator.translate(
            part["source"].tolist(),
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            num_beams=num_beams,
            max_new_tokens=max_new_tokens,
            batch_size=batch_size,
        )

        refs = part["target"].tolist()

        bleu = sacrebleu.corpus_bleu(
            preds,
            [refs],
            tokenize=_bleu_tokenizer_for_target(tgt_lang),
        ).score

        chrf = sacrebleu.corpus_chrf(
            preds,
            [refs],
            word_order=2,  # chrF++
        ).score

        rows.append(
            {
                "direction": pair,
                "examples": len(part),
                "BLEU": bleu,
                "chrF++": chrf,
            }
        )

        tmp = part.copy()
        tmp["prediction"] = preds
        predictions.append(tmp)

    metrics = pd.DataFrame(rows)
    metrics.loc[len(metrics)] = {
        "direction": "MACRO_AVERAGE",
        "examples": int(metrics["examples"].sum()),
        "BLEU": float(metrics["BLEU"].mean()),
        "chrF++": float(metrics["chrF++"].mean()),
    }

    pred_df = pd.concat(predictions, ignore_index=True)
    return metrics, pred_df


def load_adapter_for_inference(
        base_model_name: str,
        adapter_dir: Path,
        device: Optional[torch.device] = None,
):
    device = device or get_device()

    dtype = torch.float16 if device.type == "cuda" else torch.float32

    tokenizer = AutoTokenizer.from_pretrained(adapter_dir)

    base_model = AutoModelForSeq2SeqLM.from_pretrained(
        base_model_name,
        dtype=dtype,
        low_cpu_mem_usage=True,
    )

    model = PeftModel.from_pretrained(
        base_model,
        adapter_dir,
    )

    model.to(device)
    model.eval()
    model.config.use_cache = True

    return tokenizer, model


def cleanup_cuda():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
