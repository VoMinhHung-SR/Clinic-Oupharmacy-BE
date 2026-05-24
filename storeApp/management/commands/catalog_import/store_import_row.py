"""Row parsing utilities shared by store catalog import and audit."""

from __future__ import annotations

import json
import random
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from dateutil.relativedelta import relativedelta

from .store_import_packaging import normalize_single_default_unit_per_variant

COUNTRY_MAP = {
    "úc": "Úc", "australia": "Úc",
    "pháp": "Pháp", "france": "Pháp",
    "đức": "Đức", "germany": "Đức",
    "mỹ": "Mỹ", "usa": "Mỹ", "hoa kỳ": "Mỹ",
    "anh": "Anh", "uk": "Anh", "united kingdom": "Anh", "england": "Anh",
    "nhật": "Nhật Bản", "japan": "Nhật Bản",
    "hàn quốc": "Hàn Quốc", "korea": "Hàn Quốc", "south korea": "Hàn Quốc",
    "trung quốc": "Trung Quốc", "china": "Trung Quốc",
    "ấn độ": "Ấn Độ", "india": "Ấn Độ",
    "thái lan": "Thái Lan", "thailand": "Thái Lan",
    "pakistan": "Pakistan",
    "việt nam": "Việt Nam", "vietnam": "Việt Nam",
    "hungary": "Hungary",
    "thuỵ điển": "Thụy Điển", "sweden": "Thụy Điển",
    "ý": "Ý", "italy": "Ý",
    "tây ban nha": "Tây Ban Nha", "spain": "Tây Ban Nha",
}

_RANDOM_SHELF_LIFE_MONTHS = (12, 18, 24, 36)


def parse_json_field(raw, default=None):
    if default is None:
        default = []
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return default
    try:
        result = json.loads(raw)
        return result if result is not None else default
    except (json.JSONDecodeError, TypeError):
        return default


def flatten_dict(item: dict, prefix: str = "") -> dict:
    """Nested dict → flat dotted dict; lists/scalars stop recursion."""
    out: dict = {}
    for k, v in item.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten_dict(v, key))
        else:
            out[key] = v
    return out


def to_int(value, default=0) -> int:
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


def to_bool(value, default=False) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "on") if value else default


def normalize_brand(name: str) -> Optional[str]:
    if not name:
        return None
    normalized = " ".join(name.strip().split())
    return normalized or None


def extract_country(text: str) -> Optional[str]:
    if not text:
        return None
    lower = text.lower()
    for key, country in COUNTRY_MAP.items():
        if key in lower:
            return country
    return None


def extract_country_from_row(row: dict) -> Optional[str]:
    for field in ("specifications.origin", "specifications.manufacturer"):
        val = str(row.get(field) or "").strip()
        country = extract_country(val)
        if country:
            return country
    return None


def add_months(d: date, months: int) -> date:
    return d + relativedelta(months=months)


def random_import_date(today: date) -> date:
    """Random ngày nhập kho trong 6-12 tháng qua (trước today)."""
    start = add_months(today, -12)
    end = add_months(today, -6)
    delta = max((end - start).days, 1)
    return start + timedelta(days=random.randint(0, delta))


def random_shelf_life() -> str:
    return f"{random.choice(_RANDOM_SHELF_LIFE_MONTHS)} tháng"


def compute_synthetic_batch_quantity(
    quantity_in_base: int,
    pack_mult_min: int,
    pack_mult_max: int,
) -> int:
    qib = max(int(quantity_in_base or 1), 1)
    lo = max(int(pack_mult_min), 1)
    hi = max(int(pack_mult_max), lo)
    return qib * random.randint(lo, hi)


def compute_import_price_per_base_unit(price_value, quantity_in_base: int) -> Optional[Decimal]:
    if not price_value or quantity_in_base <= 0:
        return None
    try:
        return (
            Decimal(str(price_value)) / Decimal(quantity_in_base)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def clip_db_str(value, max_len: int) -> Optional[str]:
    """Truncate to model CharField max_length (import safety)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len]


def normalize_sale_unit_name(unit_name: str, default_packing: str = "") -> str:
    """
    saleUnits.unitName should be short (Hộp, Viên, …).
    Scraper sometimes puts product description in unitName — use packing fallback.
    """
    raw = (unit_name or "").strip()
    if not raw:
        return clip_db_str((default_packing or "").split()[0] if default_packing else "Gói", 50) or "Gói"

    if len(raw) > 50 or len(raw.split()) > 8 or "được dùng" in raw.lower() or ". " in raw:
        packing = (default_packing or "").strip()
        if packing:
            token = packing.split()[0]
            if token and len(token) <= 50:
                return token
        return "Gói"

    return clip_db_str(raw, 50) or "Gói"


def build_variant_payloads_from_sale_units(
    sale_units: list,
    default_packing: str,
) -> list:
    """Direct payload từ scraper saleUnits[] (giữ unitOrder + isDefault gốc)."""
    if not sale_units:
        return []

    units = []
    for su in sale_units:
        if not isinstance(su, dict):
            continue
        unit_name = normalize_sale_unit_name(
            (su.get("unitName") or "").strip(),
            default_packing=default_packing,
        )
        if not unit_name:
            continue
        units.append({
            "unit_name": unit_name,
            "unit_order": to_int(su.get("unitOrder"), 0),
            "quantity_in_base": max(to_int(su.get("quantityInBase"), 1), 1),
            "price_value": float(su.get("priceValue") or 0),
            "price_display": clip_db_str(su.get("priceDisplay"), 50),
            "is_default": bool(su.get("isDefault")),
        })

    if not units:
        return []

    units.sort(key=lambda u: (u["unit_order"], 0 if u["is_default"] else 1))
    normalize_single_default_unit_per_variant(units)
    base_unit = min(units, key=lambda u: (u["quantity_in_base"], u["unit_order"]))["unit_name"]
    packing = (default_packing or "").strip()[:100] or "Default"
    return [{"packing": packing, "base_unit": base_unit, "units": units}]


def row_text(row: dict, key: str) -> Optional[str]:
    return str(row.get(key) or "").strip() or None
