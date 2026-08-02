import json
import re
from typing import Optional

from .store_import_pricing import (
    PRICE_DISPLAY_CONSULT,
    format_price_display,
    is_consult_price_display,
    is_positive_price,
    mark_scrape_consult_unit,
)

# Canonical unit tokens (longest match first when scanning).
_UNIT_ALIASES = {
    "viên": "Viên",
    "vien": "Viên",
    "vỉ": "Vỉ",
    "vi": "Vỉ",
    "gói": "Gói",
    "goi": "Gói",
    "ống": "Ống",
    "ong": "Ống",
    "chai": "Chai",
    "lọ": "Lọ",
    "lo": "Lọ",
    "tuýp": "Tuýp",
    "tuyp": "Tuýp",
    "hộp": "Hộp",
    "hop": "Hộp",
    "thỏi": "Thỏi",
}


def _canon_unit(token: str) -> Optional[str]:
    t = (token or "").strip().lower()
    if not t:
        return None
    return _UNIT_ALIASES.get(t)


def parse_packing_hierarchy(packing: str) -> list[dict]:
    """
    Parse quy cách đóng gói → list unit từ nhỏ → lớn, mỗi phần tử:
      {unit_name, quantity_in_base}  # quantity_in_base = số đơn vị cơ sở trong unit đó

    Ví dụ:
      "Hộp 3 Vỉ x 10 Viên" → Viên=1, Vỉ=10, Hộp=30
      "Hộp 20 Gói"         → Gói=1, Hộp=20
      "Tuýp x 10g"         → Tuýp=1  (không tách khối lượng thành base bán)
      "Hộp 4 Vỉ x 5 Ống x 10ml" → Ống=1, Vỉ=5, Hộp=20
    """
    text = (packing or "").strip()
    if not text:
        return []

    # Normalize separators / junk
    raw = text
    raw = raw.replace("×", "x").replace("X", "x")
    raw = re.sub(r"\s+", " ", raw).strip()

    # Pattern: Outer N Mid x M Base  (optionally more "x qty unit")
    # e.g. Hộp 3 Vỉ x 10 Viên | Hộp 4 Vỉ x 5 Ống x 10ml
    m = re.match(
        r"^(?P<outer>Hộp|hộp|Hop|hop)\s+"
        r"(?P<n>\d+)\s*"
        # Longer tokens first (Viên before Vi) so "Hộp 60 Viên" ≠ mid=Vỉ
        r"(?P<mid>Viên|viên|Vien|vien|Vỉ|vỉ|Gói|gói|Goi|goi|Ống|ống|Ong|ong|Vi|vi)"
        r"(?:\s*x\s*(?P<m>\d+)\s*"
        r"(?P<base>Viên|viên|Vien|vien|Ống|ống|Ong|ong|Gói|gói|Goi|goi|Vỉ|vỉ))?"
        r"(?:\s*x\s*\d+\s*(?:ml|g|mg|mcg|IU|iu))?"
        r".*$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        outer = _canon_unit(m.group("outer")) or "Hộp"
        mid = _canon_unit(m.group("mid"))
        n = int(m.group("n"))
        if m.group("m") and m.group("base"):
            base = _canon_unit(m.group("base"))
            per_mid = int(m.group("m"))
            if base and mid and n > 0 and per_mid > 0:
                if n == 1:
                    # Hộp 1 Vỉ x 10 Viên → Viên + Hộp (skip duplicate Vỉ/Hộp)
                    return [
                        {"unit_name": base, "quantity_in_base": 1},
                        {"unit_name": outer, "quantity_in_base": per_mid},
                    ]
                return [
                    {"unit_name": base, "quantity_in_base": 1},
                    {"unit_name": mid, "quantity_in_base": per_mid},
                    {"unit_name": outer, "quantity_in_base": n * per_mid},
                ]
        # Hộp N Gói / Hộp N Ống / Hộp N Viên (no mid×base)
        if mid and n > 0:
            return [
                {"unit_name": mid, "quantity_in_base": 1},
                {"unit_name": outer, "quantity_in_base": n},
            ]

    # Pattern: Hộp N Vỉ x M Viên already covered; try looser "A n B" repeated
    # Single unit with size: "Tuýp x 10g", "Chai x 200ml", "Lọ 20ml", "Hộp x 15g"
    m2 = re.match(
        r"^(?P<u>Tuýp|tuýp|Tuyp|Chai|chai|Lọ|lọ|Lo|Hộp|hộp|Thỏi|thỏi)"
        r"(?:\s*x\s*\d+(?:[.,]\d+)?\s*(?:ml|g|mg)?)?"
        r"(?:\s+\d+(?:[.,]\d+)?\s*(?:ml|g|mg)?)?"
        r"\s*$",
        raw,
        flags=re.IGNORECASE,
    )
    if m2:
        u = _canon_unit(m2.group("u"))
        if u:
            return [{"unit_name": u, "quantity_in_base": 1}]

    # Fallback: first known unit token → qib=1
    for token in re.split(r"[\s/|]+", raw):
        u = _canon_unit(token)
        if u:
            return [{"unit_name": u, "quantity_in_base": 1}]
    return []


def expand_sale_units_from_pack_price(
    packing: str,
    pack_price: float,
    *,
    default_is_outer: bool = True,
    consult_display: bool = False,
) -> list[dict]:
    """
    Từ giá tổng của quy cách ngoài cùng → saleUnits đầy đủ (base → outer).

    Ví dụ packing="Hộp 3 Vỉ x 10 Viên", pack_price=105000:
      Viên qib=1  price=3500
      Vỉ   qib=10 price=35000
      Hộp  qib=30 price=105000 (isDefault)

    consult_display=True → giữ priceDisplay=CONSULT (clinic dùng priceValue).
    """
    hierarchy = parse_packing_hierarchy(packing)
    if not hierarchy:
        return []

    try:
        pack_price_f = float(pack_price or 0)
    except (TypeError, ValueError):
        pack_price_f = 0.0
    if pack_price_f <= 0:
        return []

    outer_qib = max(int(hierarchy[-1]["quantity_in_base"] or 1), 1)
    units: list[dict] = []
    for idx, level in enumerate(hierarchy):
        qib = max(int(level["quantity_in_base"] or 1), 1)
        # proportional price; round to whole VND
        price = round(pack_price_f * qib / outer_qib)
        if price <= 0 and pack_price_f > 0:
            price = 1
        is_default = (idx == len(hierarchy) - 1) if default_is_outer else (idx == 0)
        units.append(
            {
                "unitName": level["unit_name"],
                "unitOrder": idx,
                "quantityInBase": qib,
                "priceValue": float(price),
                "priceDisplay": (
                    PRICE_DISPLAY_CONSULT
                    if consult_display
                    else format_price_display(price, level["unit_name"])
                ),
                "isDefault": is_default,
                "isAvailable": True,
                "compareAtPrice": None,
                "compareAtPriceValue": None,
            }
        )
    # Ensure exactly one default
    if units:
        if not any(u.get("isDefault") for u in units):
            units[-1]["isDefault"] = True
        else:
            seen = False
            for u in units:
                if u.get("isDefault"):
                    if seen:
                        u["isDefault"] = False
                    seen = True
    return units


def reconcile_sale_units_with_packing(
    sale_units: list,
    packing: str,
    *,
    pack_price: float | None = None,
) -> list:
    """
    Nếu CSV chỉ có 1 saleUnit (thường Hộp qib=1) nhưng packing mô tả đa cấp,
    mở rộng thành Viên/Vỉ/Hộp với giá tỉ lệ từ giá gói.
    Không đụng nếu scrape đã có ≥2 unit hợp lệ với qib phân cấp.
    """
    if not isinstance(sale_units, list) or not sale_units:
        return sale_units

    hierarchy = parse_packing_hierarchy(packing)
    if len(hierarchy) < 2:
        return sale_units

    # Already multi-level with distinct qib?
    qibs = []
    for su in sale_units:
        if not isinstance(su, dict):
            continue
        try:
            qibs.append(max(int(su.get("quantityInBase") or su.get("quantity_in_base") or 1), 1))
        except (TypeError, ValueError):
            qibs.append(1)
    if len(sale_units) >= 2 and len(set(qibs)) >= 2 and max(qibs) > 1:
        return sale_units

    # Resolve pack price
    price = pack_price
    if price is None:
        for su in sale_units:
            if not isinstance(su, dict):
                continue
            try:
                pv = float(su.get("priceValue") or su.get("price_value") or 0)
            except (TypeError, ValueError):
                pv = 0.0
            if pv > 0:
                price = pv
                break
    if not price or float(price) <= 0:
        return sale_units

    was_consult = False
    for su in sale_units:
        if not isinstance(su, dict):
            continue
        pd = su.get("priceDisplay") or su.get("price_display")
        pv = su.get("priceValue") if "priceValue" in su else su.get("price_value")
        if is_consult_price_display(pd) or (
            isinstance(pv, str) and str(pv).strip().upper() == PRICE_DISPLAY_CONSULT
        ):
            was_consult = True
            break

    expanded = expand_sale_units_from_pack_price(
        packing, float(price), consult_display=was_consult
    )
    return expanded or sale_units


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
                    raw_pv = item.get("priceValue", _parse_price_value(pd))
                    consult = (
                        is_consult_price_display(pd)
                        or str(item.get("priceValue") or "").strip().upper() == "CONSULT"
                    )
                    packing = (
                        item.get("specification", "")
                        or item.get("unit", "")
                        or item.get("unitDisplay", default_packing)
                    )
                    try:
                        if (
                            isinstance(raw_pv, str)
                            and str(raw_pv).strip().upper() == PRICE_DISPLAY_CONSULT
                        ):
                            numeric_pv = 0.0
                        else:
                            numeric_pv = float(raw_pv or 0)
                    except (TypeError, ValueError):
                        numeric_pv = 0.0
                    entry = {
                        "packing": str(packing)[:100],
                        "unit_name": str(item.get("unit", item.get("unitDisplay", ""))).strip()[:50],
                        "price_display": str(pd)[:50] if not consult else None,
                        "price_value": numeric_pv,
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
