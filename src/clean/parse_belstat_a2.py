"""Парсер A2 «Качество воздуха в городских районах» (Белстат, xlsx) в tidy-CSV.

Вход:  data/raw/A2_2005-2025.xlsx  (лист на город + лист «Метаданные»)
Выход: data/processed/air_belstat_tidy.csv
Схема выхода: city, pollutant, indicator, unit, year, value, zone, source_file, source_sheet

Особенности исходных данных:
- значения: число | «…»/«...» (нет данных) | «13 (жилой район)» | «1 (жилой район) 71 (пром. район)» | «16-21» (диапазон);
- одна ячейка может описывать две зоны (жилой/промышленный район) — разбираем в отдельные строки;
- диапазоны сохраняем как среднее значение + примечание.
"""
import csv
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "A2_2005-2025.xlsx"
DST = ROOT / "data" / "processed" / "air_belstat_tidy.csv"

POLLUTANT_MAP = {
    "ТЧ 10": "PM10",
    "ТЧ 2.5": "PM2.5",
    "NO2": "NO2",
    "SO2": "SO2",
    "СО": "CO",   # кириллические С и О в исходнике!
    "CO": "CO",
    "O3": "O3",
}

VALUE_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
ZONE_RE = re.compile(r"\(([^)]+)\)")
RANGE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*$")


def parse_cell(text):
    """Возвращает список кортежей (value|None, zone|'', note|'')."""
    if text is None:
        return [(None, "", "")]
    s = str(text).strip()
    if s in ("", "…", "...", "-", "—"):
        return [(None, "", "")]
    try:
        return [(float(s.replace(",", ".")), "", "")]
    except ValueError:
        pass

    m = RANGE_RE.match(s)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        zone_m = ZONE_RE.search(s)
        zone = zone_m.group(1) if zone_m else ""
        return [((lo + hi) / 2, zone, f"диапазон {s.strip()}")]

    # защита: если вне скобок остались буквы — это не число (напр. «мкг/м3»)
    if re.search(r"[A-Za-zА-Яа-яЁё]", ZONE_RE.sub("", s)):
        return [(None, "", f"не разобрано: {s}")]

    # «1 (жилой район) 71 (пром. район)» или «13 (жилой район)» или «3-10 (жилой район)»
    parts = re.findall(r"([\d.,\s\-–—]+)\s*(?:\(([^)]+)\))?", s)
    out = []
    for num_txt, zone in parts:
        num_txt = num_txt.strip()
        if not num_txt:
            continue
        rm = RANGE_RE.match(num_txt)
        if rm:
            lo, hi = float(rm.group(1)), float(rm.group(2))
            out.append(((lo + hi) / 2, zone, f"диапазон {num_txt}"))
        else:
            vm = VALUE_RE.search(num_txt)
            if vm:
                out.append((float(vm.group(1).replace(",", ".")), zone, ""))
    return out or [(None, "", f"не разобрано: {s}")]


def norm_pollutant(header):
    h = re.sub(r"\s+", " ", str(header)).strip().upper()
    for key, code in POLLUTANT_MAP.items():
        if key.upper() in h:
            return code
    return re.sub(r"\s+", " ", str(header)).strip()


def main():
    wb = load_workbook(SRC, read_only=True, data_only=True)
    rows = []
    for sheet in wb.sheetnames:
        if sheet == "Метаданные":
            continue
        ws = wb[sheet]
        grid = list(ws.iter_rows(values_only=True))
        # строка с годами: ищем строку, где в третьей колонке 'Единица'
        year_row_idx = next(
            i for i, r in enumerate(grid) if r and len(r) > 2 and str(r[2]).strip() == "Единица"
        )
        years = {}
        for ci, cell in enumerate(grid[year_row_idx]):
            if isinstance(cell, (int, float)) and 1990 <= int(cell) <= 2100:
                years[ci] = int(cell)

        pollutant = None
        for r in grid[year_row_idx + 1:]:
            if r is None:
                continue
            label = str(r[1]).strip() if len(r) > 1 and r[1] is not None else ""
            idx = r[0]
            if not label:
                continue
            if idx is None or str(idx).strip() == "":
                pollutant = norm_pollutant(label)
                continue
            unit = str(r[2]).strip() if len(r) > 2 and r[2] is not None else ""
            for ci, year in years.items():
                raw = r[ci] if ci < len(r) else None
                for value, zone, note in parse_cell(raw):
                    rows.append({
                        "city": sheet,
                        "pollutant": pollutant,
                        "indicator": label,
                        "unit": unit,
                        "year": year,
                        "value": "" if value is None else value,
                        "zone": zone,
                        "note": note,
                        "source_file": SRC.name,
                        "source_sheet": sheet,
                    })
    wb.close()

    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    with_value = sum(1 for r in rows if r["value"] != "")
    cities = sorted({r["city"] for r in rows})
    pollutants = sorted({r["pollutant"] for r in rows})
    years = sorted({r["year"] for r in rows})
    conc = [r for r in rows if r["indicator"].startswith("Среднегодовая концентрация")]
    conc_ok = sum(1 for r in conc if r["value"] != "")
    print(f"rows total:        {total}")
    print(f"rows with value:   {with_value} ({with_value / total:.1%})")
    print(f"cities:            {len(cities)}: {', '.join(cities)}")
    print(f"pollutants:        {', '.join(pollutants)}")
    print(f"years:             {years[0]}-{years[-1]}")
    print(f"annual conc rows:  {len(conc)}, with value: {conc_ok}")
    print(f"written:           {DST}")


if __name__ == "__main__":
    sys.exit(main())
