"""
Diagnosis-aware medicine suggestions for prescribing workspace (Phase 2).
P0: doctor-scope; P1: clinic-wide fallback when doctor suggestions are sparse.
Passive mining from Diagnosis → Prescribing → PrescriptionDetail.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from typing import Iterable

from mainApp.models import Diagnosis, PrescriptionDetail
from mainApp.services.prescriber_medicine_prefs import _hydrate_variants

LOOKBACK_DIAGNOSES = 200
SIMILARITY_THRESHOLD = 0.35
TOP_SUGGESTIONS = 8
MIN_SUGGESTIONS_FOR_CLINIC_FALLBACK = 3
MIN_TOKEN_LEN = 2
DIAGNOSED_WEIGHT = 0.7
SIGN_WEIGHT = 0.3

_VN_STOPWORDS = frozenset(
    {
        "va",
        "cua",
        "voi",
        "cac",
        "cho",
        "bi",
        "co",
        "khong",
        "mot",
        "duoc",
        "la",
        "nhe",
        "tren",
        "duoi",
        "trong",
        "ngoai",
        "benh",
        "nhan",
        "the",
        "and",
        "or",
    }
)


def _remove_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def normalize_tokens(text: str) -> set[str]:
    if not text:
        return set()
    lowered = _remove_accents(str(text).lower())
    tokens = re.findall(r"[a-z0-9]+", lowered)
    return {t for t in tokens if len(t) >= MIN_TOKEN_LEN and t not in _VN_STOPWORDS}


def jaccard_similarity(a: Iterable[str], b: Iterable[str]) -> float:
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def combined_diagnosis_similarity(
    sign_a: str,
    diagnosed_a: str,
    sign_b: str,
    diagnosed_b: str,
) -> float:
    sign_sim = jaccard_similarity(normalize_tokens(sign_a), normalize_tokens(sign_b))
    diagnosed_sim = jaccard_similarity(
        normalize_tokens(diagnosed_a), normalize_tokens(diagnosed_b)
    )
    return (diagnosed_sim * DIAGNOSED_WEIGHT) + (sign_sim * SIGN_WEIGHT)


def _has_prescribing_lines(diagnosis_id: int) -> bool:
    return PrescriptionDetail.objects.filter(
        active=True,
        product_variant_id__isnull=False,
        prescribing__active=True,
        prescribing__diagnosis_id=diagnosis_id,
    ).exists()


def _matched_diagnoses(
    current: Diagnosis,
    *,
    doctor_id: int | None = None,
) -> list[tuple[Diagnosis, float]]:
    candidates = Diagnosis.objects.filter(active=True).exclude(id=current.id)
    if doctor_id is not None:
        candidates = candidates.filter(user_id=doctor_id)
    candidates = candidates.order_by("-created_date")[:LOOKBACK_DIAGNOSES]

    matched: list[tuple[Diagnosis, float]] = []
    for candidate in candidates:
        if not _has_prescribing_lines(candidate.id):
            continue
        sim = combined_diagnosis_similarity(
            current.sign,
            current.diagnosed,
            candidate.sign,
            candidate.diagnosed,
        )
        if sim >= SIMILARITY_THRESHOLD:
            matched.append((candidate, sim))
    return matched


def _matched_doctor_diagnoses(current: Diagnosis, doctor_id: int) -> list[tuple[Diagnosis, float]]:
    return _matched_diagnoses(current, doctor_id=doctor_id)


def _matched_clinic_diagnoses(current: Diagnosis) -> list[tuple[Diagnosis, float]]:
    return _matched_diagnoses(current)


def _aggregate_variants(
    matched: list[tuple[Diagnosis, float]],
    doctor_id: int,
) -> list[dict]:
    """Score variants from matched diagnoses; track doctor-owned line for prefill."""
    variant_stats: dict[int, dict] = defaultdict(
        lambda: {
            "score_sum": 0.0,
            "count": 0,
            "last_prescribed_at": None,
            "doctor_line": None,
        }
    )

    for diagnosis, sim in matched:
        lines = (
            PrescriptionDetail.objects.filter(
                active=True,
                product_variant_id__isnull=False,
                prescribing__active=True,
                prescribing__diagnosis_id=diagnosis.id,
            )
            .select_related("prescribing")
            .order_by("-created_date")
        )
        for line in lines:
            vid = line.product_variant_id
            if vid is None:
                continue
            stats = variant_stats[vid]
            stats["score_sum"] += sim
            stats["count"] += 1
            line_date = line.created_date
            if stats["last_prescribed_at"] is None or (
                line_date and line_date > stats["last_prescribed_at"]
            ):
                stats["last_prescribed_at"] = line_date
            if line.prescribing.user_id == doctor_id:
                prev = stats["doctor_line"]
                if prev is None or (
                    line_date and prev.created_date and line_date > prev.created_date
                ):
                    stats["doctor_line"] = line

    ranked: list[tuple[int, dict]] = []
    for vid, stats in variant_stats.items():
        final_score = stats["score_sum"] * math.log1p(stats["count"])
        ranked.append((vid, {**stats, "final_score": final_score}))

    ranked.sort(
        key=lambda item: (
            item[1]["final_score"],
            item[1]["last_prescribed_at"] or item[1]["doctor_line"].created_date
            if item[1]["doctor_line"]
            else item[1]["last_prescribed_at"],
        ),
        reverse=True,
    )
    return ranked[:TOP_SUGGESTIONS]


def _build_suggestion_entry(
    variant_id: int,
    stats: dict,
    variant_map: dict[int, dict],
    doctor_id: int,
    *,
    source: str = "doctor_history",
):
    variant = variant_map.get(variant_id)
    if not variant:
        return None

    doctor_line = stats.get("doctor_line")
    prefill_allowed = (
        source == "doctor_history"
        and doctor_line is not None
        and doctor_line.prescribing.user_id == doctor_id
    )

    return {
        "product_variant_id": variant_id,
        "product_variant_unit_id": doctor_line.product_variant_unit_id if prefill_allowed else None,
        "uses": doctor_line.uses if prefill_allowed else None,
        "quantity": doctor_line.quantity if prefill_allowed else None,
        "prefill_allowed": prefill_allowed,
        "match_score": round(stats["final_score"], 4),
        "prescribe_count": stats["count"],
        "last_prescribed_at": stats["last_prescribed_at"].isoformat()
        if stats["last_prescribed_at"]
        else None,
        "source": source,
        "variant": variant,
    }


def _resolve_scope(doctor_matched: int, suggestions: list[dict]) -> str:
    has_doctor = any(item["source"] == "doctor_history" for item in suggestions)
    has_clinic = any(item["source"] == "clinic_history" for item in suggestions)
    if has_doctor and has_clinic:
        return "mixed"
    if has_clinic:
        return "clinic"
    return "doctor"


def get_diagnosis_medicine_suggestions(diagnosis_id: int, doctor_id: int) -> dict:
    if not doctor_id:
        return {
            "diagnosis": None,
            "suggestions": [],
            "meta": {
                "scope": "doctor",
                "matched_diagnoses": 0,
                "clinic_matched_diagnoses": 0,
                "clinic_fallback_used": False,
            },
        }

    diagnosis = Diagnosis.objects.get(id=diagnosis_id, active=True)
    doctor_matched = _matched_doctor_diagnoses(diagnosis, doctor_id)
    doctor_ranked = _aggregate_variants(doctor_matched, doctor_id)

    clinic_matched: list[tuple[Diagnosis, float]] = []
    clinic_ranked: list[tuple[int, dict]] = []
    if len(doctor_ranked) < MIN_SUGGESTIONS_FOR_CLINIC_FALLBACK:
        clinic_matched = _matched_clinic_diagnoses(diagnosis)
        clinic_ranked = _aggregate_variants(clinic_matched, doctor_id)

    variant_ids: list[int] = []
    seen_variant_ids: set[int] = set()
    for vid, _ in doctor_ranked:
        if vid not in seen_variant_ids:
            variant_ids.append(vid)
            seen_variant_ids.add(vid)
        if len(variant_ids) >= TOP_SUGGESTIONS:
            break

    if len(variant_ids) < TOP_SUGGESTIONS:
        for vid, _ in clinic_ranked:
            if vid in seen_variant_ids:
                continue
            variant_ids.append(vid)
            seen_variant_ids.add(vid)
            if len(variant_ids) >= TOP_SUGGESTIONS:
                break

    variant_map = _hydrate_variants(variant_ids, in_stock_only=True)

    suggestions: list[dict] = []
    for vid, stats in doctor_ranked:
        entry = _build_suggestion_entry(
            vid, stats, variant_map, doctor_id, source="doctor_history"
        )
        if entry:
            suggestions.append(entry)
        if len(suggestions) >= TOP_SUGGESTIONS:
            break

    if len(suggestions) < MIN_SUGGESTIONS_FOR_CLINIC_FALLBACK:
        existing_variant_ids = {item["product_variant_id"] for item in suggestions}
        for vid, stats in clinic_ranked:
            if vid in existing_variant_ids:
                continue
            entry = _build_suggestion_entry(
                vid, stats, variant_map, doctor_id, source="clinic_history"
            )
            if entry:
                suggestions.append(entry)
                existing_variant_ids.add(vid)
            if len(suggestions) >= TOP_SUGGESTIONS:
                break

    clinic_fallback_used = any(item["source"] == "clinic_history" for item in suggestions)

    return {
        "diagnosis": {
            "id": diagnosis.id,
            "sign": diagnosis.sign,
            "diagnosed": diagnosis.diagnosed,
            "updated_at": diagnosis.updated_date.isoformat() if diagnosis.updated_date else None,
        },
        "suggestions": suggestions,
        "meta": {
            "scope": _resolve_scope(len(doctor_matched), suggestions),
            "matched_diagnoses": len(doctor_matched),
            "clinic_matched_diagnoses": len(clinic_matched),
            "clinic_fallback_used": clinic_fallback_used,
        },
    }
