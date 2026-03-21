import json
import re
from typing import Optional


def _parse_price_value(price_display: str) -> float:
    """'123.456đ' -> 123456.0"""
    if not price_display:
        return 0.0
    s = price_display.replace("đ", "").replace(".", "").replace(",", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _to_int(value, default=0) -> int:
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


def _parse_package_options(raw: str, default_packing: str = "", default_price_display: str = "", default_price_value: float = 0.0):
    """
    Parse pricing.packageOptions thành list:
      [{'packing': str, 'unit_name': str, 'price_display': str, 'price_value': float}, ...]
    """
    if not raw or not raw.strip():
        return []

    if raw.strip().startswith("["):
        try:
            items = json.loads(raw)
            if not isinstance(items, list):
                return []
            result = []
            for item in items:
                if isinstance(item, dict):
                    pd = item.get("price", item.get("priceDisplay", default_price_display))
                    pv = item.get("priceValue", _parse_price_value(pd))
                    packing = (
                        item.get("specification", "")
                        or item.get("unit", "")
                        or item.get("unitDisplay", default_packing)
                    )
                    result.append({
                        "packing": str(packing)[:100],
                        "unit_name": str(item.get("unit", item.get("unitDisplay", ""))).strip()[:50],
                        "price_display": str(pd)[:50],
                        "price_value": float(pv) if pv else 0.0,
                    })
            return result
        except (json.JSONDecodeError, TypeError):
            pass

    options = []
    for part in raw.split("|"):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"(.+?)\s+([\d.,]+đ)\s*/\s*(.+?)(?:\s*\((.+?)\))?$", part)
        if m:
            price_d = m.group(2).strip()
            spec = (m.group(4) or m.group(3) or "").strip()
            options.append({
                "packing": spec[:100] or default_packing,
                "unit_name": (m.group(3) or "").strip()[:50],
                "price_display": price_d[:50],
                "price_value": _parse_price_value(price_d),
            })
    return options


def _normalize_unit_name(unit_name: str) -> str:
    if not unit_name:
        return "unit"
    return " ".join(unit_name.strip().split()).lower()


def _extract_packing_quantity_for_base(packing: str, base_unit: str) -> Optional[int]:
    if not packing or not base_unit:
        return None
    normalized_base = re.escape(base_unit)
    match = re.search(rf"(\d+)\s*{normalized_base}\b", packing, flags=re.IGNORECASE)
    if not match:
        return None
    qty = _to_int(match.group(1), 0)
    return qty if qty > 0 else None


def _infer_quantity_in_base(base_unit: str, target_unit: str, packing: str, base_price: float, target_price: float) -> int:
    if _normalize_unit_name(base_unit) == _normalize_unit_name(target_unit):
        return 1

    quantity_from_packing = _extract_packing_quantity_for_base(packing or "", base_unit)
    if quantity_from_packing:
        return quantity_from_packing

    if base_price and target_price and target_price >= base_price:
        ratio = target_price / base_price
        rounded = int(round(ratio))
        if rounded >= 1 and abs(ratio - rounded) <= 0.15:
            return rounded

    return 1


def _build_variant_payloads(package_options: list, default_packing: str, default_price_display: str, default_price_value: float) -> list:
    """Group options theo packing để tạo 1 ProductVariant + nhiều ProductVariantUnit."""
    if not package_options:
        package_options = [{
            "packing": default_packing,
            "unit_name": "",
            "price_display": default_price_display,
            "price_value": default_price_value,
        }]

    grouped: dict = {}
    for option in package_options:
        packing = (option.get("packing") or default_packing or "").strip()[:100]
        if not packing:
            packing = "Default"

        unit_name = (option.get("unit_name") or "").strip()[:50]
        if not unit_name:
            unit_name = (packing.split()[0] if packing else "Unit").strip()[:50]
        if not unit_name:
            unit_name = "Unit"

        price_display = (option.get("price_display") or default_price_display or "").strip()[:50]
        price_value = float(option.get("price_value") or default_price_value or 0.0)

        group = grouped.setdefault(packing, {"packing": packing, "units": {}})
        unit_key = _normalize_unit_name(unit_name)
        existing = group["units"].get(unit_key)
        if existing is None or price_value < existing["price_value"]:
            group["units"][unit_key] = {
                "unit_name": unit_name,
                "price_display": price_display,
                "price_value": price_value,
            }

    payloads = []
    for packing, group in grouped.items():
        units = list(group["units"].values())
        units.sort(key=lambda item: item["price_value"] if item["price_value"] is not None else float("inf"))
        if not units:
            units = [{
                "unit_name": "Unit",
                "price_display": default_price_display,
                "price_value": default_price_value,
            }]

        base = units[0]
        base_unit = base["unit_name"]
        base_price = base["price_value"] or 0.0

        for idx, unit in enumerate(units):
            unit["unit_order"] = idx
            unit["is_default"] = idx == 0
            unit["quantity_in_base"] = _infer_quantity_in_base(
                base_unit=base_unit,
                target_unit=unit["unit_name"],
                packing=packing,
                base_price=base_price,
                target_price=unit["price_value"] or 0.0,
            )

        payloads.append({
            "packing": packing,
            "base_unit": base_unit,
            "units": units,
        })

    return payloads
