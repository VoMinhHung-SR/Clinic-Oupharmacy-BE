"""Canonical country labels for Brand.country, facets, and catalog import."""

from __future__ import annotations

from typing import Optional

COUNTRY_MAP = {
    "úc": "Úc",
    "australia": "Úc",
    "pháp": "Pháp",
    "france": "Pháp",
    "đức": "Đức",
    "germany": "Đức",
    "mỹ": "Mỹ",
    "usa": "Mỹ",
    "hoa kỳ": "Mỹ",
    "anh": "Anh",
    "uk": "Anh",
    "united kingdom": "Anh",
    "england": "Anh",
    "nhật": "Nhật Bản",
    "japan": "Nhật Bản",
    "hàn quốc": "Hàn Quốc",
    "korea": "Hàn Quốc",
    "south korea": "Hàn Quốc",
    "trung quốc": "Trung Quốc",
    "china": "Trung Quốc",
    "ấn độ": "Ấn Độ",
    "india": "Ấn Độ",
    "thái lan": "Thái Lan",
    "thailand": "Thái Lan",
    "pakistan": "Pakistan",
    "việt nam": "Việt Nam",
    "vietnam": "Việt Nam",
    "vn": "Việt Nam",
    "hungary": "Hungary",
    "thuỵ điển": "Thụy Điển",
    "sweden": "Thụy Điển",
    "ý": "Ý",
    "italy": "Ý",
    "tây ban nha": "Tây Ban Nha",
    "spain": "Tây Ban Nha",
    "ba lan": "Ba Lan",
    "poland": "Ba Lan",
    "đan mạch": "Đan Mạch",
    "denmark": "Đan Mạch",
}

_KNOWN_BY_CASEFOLD = {value.casefold(): value for value in set(COUNTRY_MAP.values())}


def extract_country(text: str) -> Optional[str]:
    """Substring match against COUNTRY_MAP keys (import / free-text origin)."""
    if not text:
        return None
    lower = text.lower()
    for key, country in COUNTRY_MAP.items():
        if key in lower:
            return country
    return None


def normalize_country_label(text: str) -> Optional[str]:
    """
    Return canonical country label, or None for junk / unknown.

    Accepts exact known labels (case-insensitive) or substring map hits.
    Rejects packing-size strings like "Hộp x 15ml".
    """
    if not text:
        return None
    stripped = " ".join(str(text).strip().split())
    if not stripped:
        return None
    exact = _KNOWN_BY_CASEFOLD.get(stripped.casefold())
    if exact:
        return exact
    return extract_country(stripped)


def extract_country_from_row(row: dict) -> Optional[str]:
    for field in ("specifications.origin", "specifications.manufacturer"):
        val = str(row.get(field) or "").strip()
        country = extract_country(val)
        if country:
            return country
    return None


def parse_csv_ints(raw) -> list[int]:
    """Parse `1,2,3` → sorted unique ints (invalid tokens skipped)."""
    if raw is None or raw == "":
        return []
    ids: set[int] = set()
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except (TypeError, ValueError):
            continue
    return sorted(ids)


def parse_csv_strings(raw) -> list[str]:
    """Parse comma-separated strings → unique values preserving first-seen order."""
    if raw is None or raw == "":
        return []
    seen: set[str] = set()
    out: list[str] = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part or part in seen:
            continue
        seen.add(part)
        out.append(part)
    return out
