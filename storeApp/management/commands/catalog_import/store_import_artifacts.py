"""
Artifact + optional source-CSV annotation for scrape rows that lack a real price.

Writes:
  - Aggregate report CSV under artifacts/
  - Split views: by phase (old|new), by L0, by phase+L0, unique mid
  - Optional column `import.scrapePriceGap` on source CSV rows (consult|zero|missing)
"""

from __future__ import annotations

import csv
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


PRICE_GAP_COLUMN = "import.scrapePriceGap"

ARTIFACT_FIELDNAMES = [
    "source_file",
    "csv_line",
    "mid",
    "slug",
    "name",
    "unit_name",
    "reason",
    "l0_slug",
]

PRODUCT_FIELDNAMES = [
    "mid",
    "slug",
    "name",
    "reason",
    "l0_slug",
    "source_phase",
    "unit_count",
    "sample_source_file",
    "sample_csv_line",
]


@dataclass
class MissingPriceHit:
    source_file: str
    csv_line: int  # 1-based file line (header = 1)
    row_index: int  # 0-based among data rows
    mid: str
    slug: str
    name: str
    unit_name: str
    reason: str  # consult | zero | missing
    l0_slug: str = ""


def detect_source_phase(source_file: str) -> str:
    """Return old | new | other from path (.../test/data/{old|new}/...)."""
    parts = Path(source_file).parts
    for i, part in enumerate(parts):
        if part == "data" and i + 1 < len(parts):
            nxt = parts[i + 1].lower()
            if nxt in ("old", "new"):
                return nxt
    lowered = source_file.replace("\\", "/").lower()
    if "/old/" in lowered:
        return "old"
    if "/new/" in lowered:
        return "new"
    return "other"


def safe_slug(value: str, *, fallback: str = "unknown") -> str:
    text = (value or "").strip().lower() or fallback
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or fallback


def hit_to_row(hit: MissingPriceHit) -> dict:
    return {
        "source_file": hit.source_file,
        "csv_line": hit.csv_line,
        "mid": hit.mid,
        "slug": hit.slug,
        "name": hit.name,
        "unit_name": hit.unit_name,
        "reason": hit.reason,
        "l0_slug": hit.l0_slug,
    }


def _write_csv(path: str, fieldnames: list[str], rows: Iterable[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def split_no_price_hits(
    hits: list[MissingPriceHit],
    out_dir: str,
    *,
    stamp: str | None = None,
) -> dict[str, str]:
    """
    Write split artifact views under out_dir.

    Layout:
      no_price_all_{stamp}.csv
      no_price_products_{stamp}.csv          # 1 row / mid
      by_phase/{old|new|other}.csv
      by_l0/{l0}.csv
      by_phase_l0/{phase}__{l0}.csv
      SUMMARY.txt
    """
    if not hits:
        return {}

    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    written: dict[str, str] = {}

    all_path = os.path.join(out_dir, f"no_price_all_{stamp}.csv")
    _write_csv(all_path, ARTIFACT_FIELDNAMES, (hit_to_row(h) for h in hits))
    written["all"] = all_path

    by_phase: dict[str, list[dict]] = defaultdict(list)
    by_l0: dict[str, list[dict]] = defaultdict(list)
    by_phase_l0: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_mid: dict[str, list[MissingPriceHit]] = defaultdict(list)

    for hit in hits:
        row = hit_to_row(hit)
        phase = detect_source_phase(hit.source_file)
        l0 = safe_slug(hit.l0_slug or "unknown")
        by_phase[phase].append(row)
        by_l0[l0].append(row)
        by_phase_l0[(phase, l0)].append(row)
        key = hit.mid or hit.slug or f"{hit.source_file}:{hit.csv_line}"
        by_mid[key].append(hit)

    phase_dir = os.path.join(out_dir, "by_phase")
    for phase, rows in sorted(by_phase.items()):
        path = os.path.join(phase_dir, f"{phase}.csv")
        _write_csv(path, ARTIFACT_FIELDNAMES, rows)
        written[f"phase:{phase}"] = path

    l0_dir = os.path.join(out_dir, "by_l0")
    for l0, rows in sorted(by_l0.items()):
        path = os.path.join(l0_dir, f"{l0}.csv")
        _write_csv(path, ARTIFACT_FIELDNAMES, rows)
        written[f"l0:{l0}"] = path

    phase_l0_dir = os.path.join(out_dir, "by_phase_l0")
    for (phase, l0), rows in sorted(by_phase_l0.items()):
        path = os.path.join(phase_l0_dir, f"{phase}__{l0}.csv")
        _write_csv(path, ARTIFACT_FIELDNAMES, rows)
        written[f"phase_l0:{phase}__{l0}"] = path

    reason_priority = {"consult": 3, "zero": 2, "missing": 1}
    product_rows: list[dict] = []
    for mid, group in by_mid.items():
        best = max(group, key=lambda h: reason_priority.get(h.reason, 0))
        product_rows.append(
            {
                "mid": best.mid or mid,
                "slug": best.slug,
                "name": best.name,
                "reason": best.reason,
                "l0_slug": best.l0_slug,
                "source_phase": detect_source_phase(best.source_file),
                "unit_count": len(group),
                "sample_source_file": best.source_file,
                "sample_csv_line": best.csv_line,
            }
        )
    product_rows.sort(key=lambda r: (r["source_phase"], r["l0_slug"], r["slug"] or r["mid"]))
    products_path = os.path.join(out_dir, f"no_price_products_{stamp}.csv")
    _write_csv(products_path, PRODUCT_FIELDNAMES, product_rows)
    written["products"] = products_path

    reason_counts = Counter(h.reason for h in hits)
    phase_counts = Counter(detect_source_phase(h.source_file) for h in hits)
    l0_counts = Counter(safe_slug(h.l0_slug or "unknown") for h in hits)
    summary_path = os.path.join(out_dir, f"SUMMARY_{stamp}.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"no_price artifact split @ {stamp}\n")
        f.write(f"unit_hits={len(hits)}  unique_products={len(product_rows)}\n\n")
        f.write("by_reason:\n")
        for k, v in reason_counts.most_common():
            f.write(f"  {k}: {v}\n")
        f.write("\nby_phase:\n")
        for k, v in phase_counts.most_common():
            f.write(f"  {k}: {v}\n")
        f.write("\nby_l0:\n")
        for k, v in l0_counts.most_common():
            f.write(f"  {k}: {v}\n")
        f.write("\npriority hint:\n")
        f.write("  P1  by_l0 non-thuoc small slices (manual / search enrich)\n")
        f.write("  P2  by_l0/duoc-mi-pham + thuc-pham-chuc-nang (under data/new)\n")
        f.write("  P3  by_l0/thuoc (bulk CONSULT — policy/re-scrape)\n")
        f.write("\nnote: CSV SoT is storeApp/test/data/new/<l0>/ (old/ merged away).\n")
    written["summary"] = summary_path
    return written


def split_existing_artifact_csv(artifact_path: str, out_dir: str | None = None) -> dict[str, str]:
    """Split an existing aggregate no_price CSV into phase/L0/product views."""
    artifact_path = os.path.abspath(artifact_path)
    out_dir = out_dir or os.path.join(os.path.dirname(artifact_path), "split")
    hits: list[MissingPriceHit] = []
    with open(artifact_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hits.append(
                MissingPriceHit(
                    source_file=str(row.get("source_file") or ""),
                    csv_line=int(row.get("csv_line") or 0),
                    row_index=0,
                    mid=str(row.get("mid") or ""),
                    slug=str(row.get("slug") or ""),
                    name=str(row.get("name") or ""),
                    unit_name=str(row.get("unit_name") or ""),
                    reason=str(row.get("reason") or "missing"),
                    l0_slug=str(row.get("l0_slug") or ""),
                )
            )
    stamp = Path(artifact_path).stem.replace("no_price_products_", "").replace("no_price_all_", "")
    if stamp == Path(artifact_path).stem:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return split_no_price_hits(hits, out_dir, stamp=stamp)


@dataclass
class MissingPriceReporter:
    """Collects no-price hits during an import run."""

    hits: list[MissingPriceHit] = field(default_factory=list)
    # source_file -> {row_index -> worst/primary reason}
    _row_reasons: dict[str, dict[int, str]] = field(default_factory=dict)

    def add(self, hit: MissingPriceHit) -> None:
        self.hits.append(hit)
        by_row = self._row_reasons.setdefault(hit.source_file, {})
        # Prefer consult > zero > missing when multiple units on one row
        priority = {"consult": 3, "zero": 2, "missing": 1}
        prev = by_row.get(hit.row_index)
        if prev is None or priority.get(hit.reason, 0) > priority.get(prev, 0):
            by_row[hit.row_index] = hit.reason

    def write_artifact(self, out_path: str, *, append: bool = False) -> str:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        file_exists = append and os.path.isfile(out_path) and os.path.getsize(out_path) > 0
        mode = "a" if file_exists else "w"
        with open(out_path, mode, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=ARTIFACT_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            for hit in self.hits:
                writer.writerow(hit_to_row(hit))
        return out_path

    def write_split_artifacts(self, aggregate_path: str) -> dict[str, str]:
        """
        Re-read the full aggregate file (supports multi-phase append) and split
        under artifacts/current/split/ (never SUMMARY_local / by_phase old-new root).
        """
        agg_dir = os.path.dirname(aggregate_path) or "."
        # Prefer .../artifacts/current/split
        out_dir = os.path.join(agg_dir, "split")
        if not os.path.isfile(aggregate_path):
            return split_no_price_hits(self.hits, out_dir)
        return split_existing_artifact_csv(aggregate_path, out_dir=out_dir)

    def annotate_source_csvs(self) -> list[str]:
        """
        Add/update `import.scrapePriceGap` on rows that needed synthetic pricing.
        Returns list of rewritten file paths.
        """
        rewritten: list[str] = []
        for source_file, row_map in self._row_reasons.items():
            if not source_file.endswith(".csv") or not os.path.isfile(source_file):
                continue
            if not row_map:
                continue
            if self._annotate_one_csv(source_file, row_map):
                rewritten.append(source_file)
        return rewritten

    @staticmethod
    def _annotate_one_csv(path: str, row_reasons: dict[int, str]) -> bool:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return False
            fieldnames = list(reader.fieldnames)
            if PRICE_GAP_COLUMN not in fieldnames:
                fieldnames.append(PRICE_GAP_COLUMN)
            rows = list(reader)

        changed = False
        for idx, row in enumerate(rows):
            reason = row_reasons.get(idx)
            if not reason:
                continue
            if row.get(PRICE_GAP_COLUMN) != reason:
                row[PRICE_GAP_COLUMN] = reason
                changed = True

        if not changed:
            return False

        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path, path)
        return True


def default_artifact_path(base_dir: str) -> str:
    """Aggregate no-price CSV under artifacts/current/ (stable folder, stamped file)."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(
        base_dir,
        "storeApp",
        "test",
        "data",
        "artifacts",
        "current",
        f"no_price_all_{stamp}.csv",
    )


def mid_from_row(row: dict) -> str:
    return str(row.get("basicInfo.sku") or row.get("basicInfo.mid") or "").strip()


def slug_from_row(row: dict) -> str:
    return str(row.get("basicInfo.slug") or "").strip()


def name_from_row(row: dict) -> str:
    return str(row.get("basicInfo.name") or "").strip()[:200]


def l0_slug_from_category_array(category_array: Iterable) -> str:
    for item in category_array or []:
        if isinstance(item, dict):
            return str(item.get("slug") or "").strip()
    return ""
