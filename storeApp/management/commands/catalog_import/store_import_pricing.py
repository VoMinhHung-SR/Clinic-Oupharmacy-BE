"""
Smart synthetic pricing for store_import_csv when scrape price is missing or zero.

Strategy per variant (units list):
  1) Treat price_value <= 0 and scrape "CONSULT" as missing (no listed price).
  2) Infer from sibling units with known price (median VND per base unit × quantity_in_base).
  3) Row numeric fallback fills clinic price_value; CONSULT units keep storefront CONSULT.
  4) Tiered random per base unit by unit_name (viên/gói vs hộp vs thùng) for remaining gaps.

Dual display model (CONSULT scrape / clinic ref fill):
  - storefront: price_display = "CONSULT" (FE shows Liên hệ)
  - clinic kê toa: price_value = numeric VND (synthetic or manual_ref)
"""

from __future__ import annotations

import random
import re
import unicodedata
from typing import Optional

PRICE_DISPLAY_CONSULT = "CONSULT"

# VND per đơn vị cơ sở (before × quantity_in_base)
_UNIT_TIER_RULES: tuple[tuple[tuple[str, ...], int, int], ...] = (
    (("viên", "vien", "vien nang", "viên nang"), 400, 8_000),
    (("gói", "goi", "gói nhỏ", "goi nho"), 1_000, 15_000),
    (("ml", "gram", "g", "ống", "ong", "chai nhỏ"), 300, 6_000),
    (("vỉ", "vi", "vỉ x", "vi x"), 2_000, 25_000),
    (("hộp", "hop", "lọ", "lo", "tuýp", "tuyp", "chai"), 800, 22_000),
    (("thùng", "thung", "combo", "set", "hộp lớn"), 2_500, 45_000),
)
_DEFAULT_PER_BASE_RANGE = (500, 18_000)
_VND_ROUND_STEP = 1_000
_MIN_UNIT_PRICE_VND = 1_000


def _normalize_unit_key(unit_name: str) -> str:
    if not unit_name:
        return ""
    text = unicodedata.normalize("NFD", str(unit_name).strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def _per_base_range_for_unit(unit_name: str) -> tuple[int, int]:
    key = _normalize_unit_key(unit_name)
    for tokens, lo, hi in _UNIT_TIER_RULES:
        if any(tok in key for tok in tokens):
            return lo, hi
    return _DEFAULT_PER_BASE_RANGE


def is_positive_price(value) -> bool:
    try:
        return float(value or 0) > 0
    except (TypeError, ValueError):
        return False


def is_consult_price_display(value) -> bool:
    if value is None:
        return False
    return str(value).strip().upper() == PRICE_DISPLAY_CONSULT


def scrape_price_was_consult(unit: dict) -> bool:
    """Scrape marked CONSULT — fill clinic price_value; keep storefront CONSULT display."""
    return bool(unit.get("scrape_was_consult"))


def mark_scrape_consult_unit(unit: dict) -> None:
    """Normalize unit from CONSULT scrape; keep positive clinic price_value if present."""
    keep_value = unit.get("price_value")
    unit["scrape_was_consult"] = True
    unit["price_display"] = None
    if is_positive_price(keep_value) and not (
        isinstance(keep_value, str) and str(keep_value).strip().upper() == PRICE_DISPLAY_CONSULT
    ):
        unit["price_value"] = float(keep_value)
    else:
        unit["price_value"] = 0


def apply_consult_storefront_display(unit: dict) -> None:
    """Keep storefront CONSULT while allowing a numeric clinic price_value."""
    unit["scrape_was_consult"] = True
    unit["price_display"] = PRICE_DISPLAY_CONSULT


def row_uses_consult_storefront(row: dict | None) -> bool:
    """
    Row should show CONSULT on store even when clinic has a filled price_value.

    True when:
      - scrape gap annotated as consult
      - row-level price display/value is CONSULT
      - import.priceSource is manual_ref* (clinic ref fill for consult catalog)
    """
    if not row:
        return False
    gap = str(row.get("import.scrapePriceGap") or "").strip().lower()
    if gap == "consult":
        return True
    if is_consult_price_display(row.get("pricing.priceDisplay")):
        return True
    if isinstance(row.get("pricing.priceValue"), str) and str(
        row.get("pricing.priceValue")
    ).strip().upper() == PRICE_DISPLAY_CONSULT:
        return True
    source = str(row.get("import.priceSource") or "").strip().lower()
    if source.startswith("manual_ref"):
        return True
    return False


def force_consult_storefront_on_units(units: list) -> None:
    """Force CONSULT price_display after pricing; do not leave scrape_was_consult."""
    for u in units or []:
        if not isinstance(u, dict):
            continue
        u["price_display"] = PRICE_DISPLAY_CONSULT
        u.pop("scrape_was_consult", None)


def classify_unit_scrape_price_gap(unit: dict) -> Optional[str]:
    """
    Classify scrape price gap before synthetic fill.

    Returns:
      - "consult" — display/value is CONSULT (or already marked scrape_was_consult)
      - "zero" — numeric price <= 0
      - "missing" — empty / undefined / non-numeric
      - None — has a positive scrape price
    """
    if scrape_price_was_consult(unit):
        return "consult"

    display = unit.get("price_display")
    value = unit.get("price_value")

    if is_consult_price_display(display) or (
        isinstance(value, str) and str(value).strip().upper() == "CONSULT"
    ):
        return "consult"

    if value is None or (isinstance(value, str) and not str(value).strip()):
        if display is None or (isinstance(display, str) and not str(display).strip()):
            return "missing"
        if is_consult_price_display(display):
            return "consult"
        return "missing"

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "missing"

    if numeric <= 0:
        return "zero"
    return None


def collect_unit_price_gaps(units: list) -> list[tuple[dict, str]]:
    """Return [(unit, reason), ...] for units that need synthetic pricing."""
    gaps: list[tuple[dict, str]] = []
    for unit in units or []:
        if not isinstance(unit, dict):
            continue
        reason = classify_unit_scrape_price_gap(unit)
        if reason:
            gaps.append((unit, reason))
    return gaps


def round_vnd(amount: float) -> float:
    rounded = max(_MIN_UNIT_PRICE_VND, int(round(amount / _VND_ROUND_STEP)) * _VND_ROUND_STEP)
    return float(rounded)


def smart_random_unit_price(unit_name: str, quantity_in_base: int) -> float:
    qib = max(int(quantity_in_base or 1), 1)
    lo, hi = _per_base_range_for_unit(unit_name)
    per_base = random.randint(lo, hi)
    return round_vnd(per_base * qib)


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _infer_missing_from_siblings(units: list) -> None:
    per_base_samples: list[float] = []
    for u in units:
        if not is_positive_price(u.get("price_value")):
            continue
        qib = max(int(u.get("quantity_in_base") or 1), 1)
        per_base_samples.append(float(u["price_value"]) / qib)

    median_per_base = _median(per_base_samples)
    if median_per_base is None:
        return

    for u in units:
        if is_positive_price(u.get("price_value")):
            continue
        qib = max(int(u.get("quantity_in_base") or 1), 1)
        u["price_value"] = round_vnd(median_per_base * qib)


def _apply_row_fallback(units: list, fallback_price: float, fallback_display: str = "") -> None:
    if not is_positive_price(fallback_price):
        return

    default_u = None
    for u in units:
        if u.get("is_default"):
            default_u = u
            break
    if default_u is None and units:
        default_u = units[0]

    def_qib = max(int((default_u or {}).get("quantity_in_base") or 1), 1)
    per_base = float(fallback_price) / def_qib
    fallback_is_consult = is_consult_price_display(fallback_display)

    for u in units:
        if is_positive_price(u.get("price_value")):
            continue
        # Pure CONSULT row fallback (no numeric) — leave for smart-random clinic fill
        if scrape_price_was_consult(u) and fallback_is_consult:
            continue
        qib = max(int(u.get("quantity_in_base") or 1), 1)
        u["price_value"] = round_vnd(per_base * qib)
        if scrape_price_was_consult(u) or fallback_is_consult:
            apply_consult_storefront_display(u)
        elif not u.get("price_display"):
            u["price_display"] = format_price_display(u["price_value"], u.get("unit_name", ""))


def format_price_display(value: float, unit_name: str = "", *, max_len: int = 50) -> str:
    s = f"{int(value):,}".replace(",", ".") + "đ"
    if unit_name:
        short_unit = str(unit_name).strip()[:20]
        s = f"{s} / {short_unit}"
    return s[:max_len] if len(s) > max_len else s


def ensure_unit_pricing(
    units: list,
    fallback_price: float = 0,
    fallback_display: str = "",
    *,
    use_smart_random: bool = True,
) -> None:
    """
    Fill missing/zero unit prices in-place.

    CONSULT scrape / clinic-ref units:
      - price_value ← sibling infer / smart random / numeric fallback (clinic)
      - price_display stays "CONSULT" (storefront)
    Listed scrape prices: both value + VND display.
    """
    if not units:
        return

    for u in units:
        if is_consult_price_display(u.get("price_display")) or (
            isinstance(u.get("price_value"), str)
            and str(u.get("price_value")).strip().upper() == PRICE_DISPLAY_CONSULT
        ):
            # Preserve existing positive clinic value if already filled (manual_ref re-import)
            keep_value = u.get("price_value")
            mark_scrape_consult_unit(u)
            if is_positive_price(keep_value) and not (
                isinstance(keep_value, str)
                and str(keep_value).strip().upper() == PRICE_DISPLAY_CONSULT
            ):
                u["price_value"] = float(keep_value)
        elif not is_positive_price(u.get("price_value")):
            u["price_value"] = 0

    _infer_missing_from_siblings(units)
    _apply_row_fallback(units, fallback_price, fallback_display)

    for u in units:
        was_consult = scrape_price_was_consult(u)

        if is_positive_price(u.get("price_value")):
            if was_consult:
                apply_consult_storefront_display(u)
            elif not u.get("price_display") or is_consult_price_display(u.get("price_display")):
                u["price_display"] = format_price_display(
                    float(u["price_value"]), u.get("unit_name", "")
                )
            continue

        if use_smart_random:
            u["price_value"] = smart_random_unit_price(
                u.get("unit_name", ""),
                u.get("quantity_in_base", 1),
            )
        else:
            u["price_value"] = float(random.randint(10_000, 500_000))

        if was_consult:
            apply_consult_storefront_display(u)
        elif not u.get("price_display") or is_consult_price_display(u.get("price_display")):
            u["price_display"] = format_price_display(
                float(u["price_value"]), u.get("unit_name", "")
            )

    for u in units:
        # Drop transient flag; storefront signal is price_display == CONSULT
        u.pop("scrape_was_consult", None)
