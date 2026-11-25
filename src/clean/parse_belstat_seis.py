"""Универсальный парсер файлов Белстата SEIS («Временные ряды данных») в tidy-CSV.

Обрабатывает файлы с листами, где годы — колонки, показатели — строки:
I1 (отходы), C1 (водные ресурсы), C3 (водопользование), C16 (сточные воды), C11 (биогены).

Выход: data/processed/<имя_файла>_tidy.csv
Схема: dataset, sheet, block, indicator, unit, year, value, zone, note, source_file, source_sheet

Разбор значений переиспользует parse_cell из parse_belstat_a2.py.
"""
import csv
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_belstat_a2 import parse_cell  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
DST_DIR = ROOT / "data" / "processed"

DEFAULT_FILES = ["I1-2005-2025.xlsx", "C1-1990-2024.xlsx", "C3-1990-2025.xlsx",
                 "C16-2005-2025.xlsx", "C11-2005-2025.xlsx"]


def parse_sheet(ws, dataset, src_name):
    grid = list(ws.iter_rows(values_only=True))
    year_row_idx = unit_col = None
    for i, row in enumerate(grid):
        if row:
            for ci, cell in enumerate(row):
                if cell is not None and str(cell).strip() == "Единица":
                    year_row_idx, unit_col = i, ci
                    break
        if year_row_idx is not None:
            break
    if year_row_idx is None:
        return []

    years = {}
    for ci, cell in enumerate(grid[year_row_idx]):
        if isinstance(cell, (int, float)) and 1990 <= int(cell) <= 2100:
            years[ci] = int(cell)

    rows = []
    block = ""
    label_col = unit_col - 1
    for r in grid[year_row_idx + 1:]:
        if r is None:
            continue
        label = str(r[label_col]).strip() if len(r) > label_col and r[label_col] is not None else ""
        if not label:
            continue
        idx = r[0] if len(r) > 0 else None
        if idx is None or str(idx).strip() == "":
            if not label.startswith(("Примечание", "\"…\"", "«…»")):
                block = label.replace("\n", " ")
            continue
        unit = str(r[unit_col]).strip() if len(r) > unit_col and r[unit_col] is not None else ""
        for ci, year in years.items():
            raw = r[ci] if ci < len(r) else None
            for value, zone, note in parse_cell(raw):
                rows.append({
                    "dataset": dataset,
                    "sheet": ws.title,
                    "block": block,
                    "indicator": label,
                    "unit": unit,
                    "year": year,
                    "value": "" if value is None else value,
                    "zone": zone,
                    "note": note,
                    "source_file": src_name,
                    "source_sheet": ws.title,
                })
    return rows


def main():
    files = sys.argv[1:] or DEFAULT_FILES
    DST_DIR.mkdir(parents=True, exist_ok=True)
    summary = []
    for fname in files:
        path = RAW / fname
        if not path.exists():
            print(f"SKIP (нет файла): {path}")
            continue
        wb = load_workbook(path, read_only=True, data_only=True)
        rows = []
        for sheet in wb.sheetnames:
            if sheet == "Метаданные":
                continue
            rows.extend(parse_sheet(wb[sheet], path.stem, path.name))
        wb.close()
        if not rows:
            print(f"SKIP (нет данных): {fname}")
            continue
        dst = DST_DIR / f"{path.stem}_tidy.csv"
        with open(dst, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        total = len(rows)
        ok = sum(1 for r in rows if r["value"] != "")
        bad = sum(1 for r in rows if r["note"].startswith("не разобрано"))
        yrs = sorted({r["year"] for r in rows})
        summary.append((fname, total, ok, bad, f"{yrs[0]}-{yrs[-1]}", len({r["indicator"] for r in rows})))
        print(f"{fname}: rows={total}, with_value={ok} ({ok / total:.1%}), "
              f"unparsed={bad}, years={yrs[0]}-{yrs[-1]}, indicators={summary[-1][5]} -> {dst.name}")

    print("\n== СВОДКА КАЧЕСТВА ==")
    print(f"{'файл':28} {'строк':>6} {'с знач.':>8} {'брак':>5} {'годы':>12}")
    for fname, total, ok, bad, yr, _ in summary:
        print(f"{fname:28} {total:>6} {ok:>8} {bad:>5} {yr:>12}")


if __name__ == "__main__":
    sys.exit(main())
