import json
import re
from typing import Optional

from .store_import_pricing import (
    is_consult_price_display,
    is_positive_price,
    mark_scrape_consult_unit,
)


def _parse_price_value(price_display: str) -> float:
    """'123.456đ' / '330.000đ / Hộp' / 'CONSULT' -> float VND (0 if unknown)."""
    if not price_display:
        return 0.0
    s = str(price_display).strip()
    if s.upper() == "CONSULT":
        return 0.0
    if "/" in s:
        s = s.split("/", 1)[0].strip()
    s = s.replace("đ", "").replace(".", "").replace(",", "").strip()
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
                    consult = (
                        is_consult_price_display(pd)
                        or str(item.get("priceValue") or "").strip().upper() == "CONSULT"
                    )
                    packing = (
                        item.get("specification", "")
                        or item.get("unit", "")
                        or item.get("unitDisplay", default_packing)
                    )
                    entry = {
                        "packing": str(packing)[:100],
                        "unit_name": str(item.get("unit", item.get("unitDisplay", ""))).strip()[:50],
                        "price_display": str(pd)[:50] if not consult else None,
                        "price_value": 0.0 if consult else (float(pv) if pv else 0.0),
                    }
                    if consult:
                        mark_scrape_consult_unit(entry)
                    result.append(entry)
            return result
        except (json.JSONDecodeError, TypeError):
            pass

    options = []
    for part in raw.split("|"):
        part = part.strip()
        if not part:
            continue
        consult_m = re.match(r"^CONSULT\s*\((.+?)\)\s*$", part, flags=re.IGNORECASE)
        if consult_m:
            unit_name = (consult_m.group(1) or "").strip()[:50]
            entry = {
                "packing": default_packing,
                "unit_name": unit_name or (default_packing.split()[0] if default_packing else "Unit"),
                "price_display": None,
                "price_value": 0.0,
            }
            mark_scrape_consult_unit(entry)
            options.append(entry)
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
        option_consult = option.get("scrape_was_consult") or is_consult_price_display(price_display)
        replace = existing is None
        if not replace and option_consult:
            replace = not is_positive_price(existing.get("price_value"))
        elif not replace:
            replace = price_value < float(existing.get("price_value") or 0)
        if replace:
            entry = {
                "unit_name": unit_name,
                "price_display": price_display,
                "price_value": price_value,
            }
            if option_consult:
                mark_scrape_consult_unit(entry)
            group["units"][unit_key] = entry

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
        infer_base_unit = base["unit_name"]
        base_price = base["price_value"] or 0.0

        for idx, unit in enumerate(units):
            unit["unit_order"] = idx
            unit["is_default"] = idx == 0
            unit["quantity_in_base"] = _infer_quantity_in_base(
                base_unit=infer_base_unit,
                target_unit=unit["unit_name"],
                packing=packing,
                base_price=base_price,
                target_price=unit["price_value"] or 0.0,
            )

        normalize_single_default_unit_per_variant(units)
        # Variant.base_unit = đơn vị cơ sở nhỏ nhất (old CSV / packageOptions refactor path)
        smallest_base = min(units, key=lambda u: (u.get("quantity_in_base", 1), u.get("unit_order", 0)))
        payloads.append({
            "packing": packing,
            "base_unit": smallest_base["unit_name"],
            "units": units,
        })

    return payloads


def normalize_single_default_unit_per_variant(units: list[dict]) -> None:
    """
    Chuẩn hóa is_default trên list unit của **một** variant (mutate in-place).

    - Không có default nào → gán default cho unit có unit_order nhỏ nhất (rồi id ổn định).
    - Nhiều default → giữ một: ưu tiên unit_order thấp nhất trong các unit đang is_default=True.
    - Đúng một default → các unit còn lại False (đồng bộ rõ ràng).
    """
    if not units:
        return
    flagged = [i for i, u in enumerate(units) if bool(u.get("is_default"))]

    def _order_key(i: int):
        return (units[i].get("unit_order", 0), i)

    if len(flagged) == 1:
        keep = flagged[0]
    elif len(flagged) == 0:
        keep = min(range(len(units)), key=_order_key)
    else:
        keep = min(flagged, key=_order_key)

    for i, u in enumerate(units):
        u["is_default"] = i == keep


def reconcile_single_default_variant_units_in_db(variant, using: str = "store") -> None:
    """
    Trên DB: đảm bảo đúng **một** ProductVariantUnit có is_default=True / variant.
    Dùng sau import hoặc khi dữ liệu lệch (0 hoặc >1 default).

    Ưu tiên giữ một default hiện có có unit_order nhỏ nhất; nếu không có default nào thì chọn unit_order nhỏ nhất.
    """
    from storeApp.models import ProductVariantUnit

    rows = list(
        ProductVariantUnit.objects.using(using)
        .filter(variant=variant)
        .order_by("unit_order", "id")
    )
    if not rows:
        return

    defaults = [u for u in rows if u.is_default]
    if len(defaults) == 1:
        return

    if len(defaults) >= 2:
        keep = min(defaults, key=lambda u: (u.unit_order, u.id))
    else:
        keep = rows[0]

    for u in rows:
        u.is_default = u.id == keep.id

    ProductVariantUnit.objects.using(using).bulk_update(rows, ["is_default"], batch_size=500)
