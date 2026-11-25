"""Парсер RTF Минприроды «Отчёт о наличии, образовании и движении отходов по областям».

Вход:  data/raw/minpriroda/otxody_2025_po_oblastjam.rtf
Выход: data/processed/waste_regions_2025_tidy.csv (long format, год 2025)

Особенности RTF:
- кириллица закодирована как \\'hh (байты cp1251) и \\uNNNN;
- ячейки таблицы разделены управляющими словами (\\cell, \\tab), которые при
  простом удалении «склеивают» числа;
- инвариант исходника: все числа с тремя знаками после запятой («666,345»),
  что позволяет разбирать слитые последовательности регулярным выражением;
- встроенный бинарный объект в конце файла — не текст, отбрасывается.
Валидация: «Удалено — всего» = сумма четырёх подытогов «из них» (точность 0.05).
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "minpriroda" / "otxody_2025_po_oblastjam.rtf"
DST = ROOT / "data" / "processed" / "waste_regions_2025_tidy.csv"

COLUMNS = [
    "Наличие на начало года", "Образовано", "Использовано, передано",
    "Удалено - всего", "Удалено - на объекты хранения", "Удалено - захоронено",
    "Удалено - хранение на территории предприятия", "Удалено - обезврежено",
    "Наличие на конец года",
]
REGION_KEYS = [
    ("Брестскаяобласть", "Брестская область"),
    ("Витебскаяобласть", "Витебская область"),
    ("Гомельскаяобласть", "Гомельская область"),
    ("Гродненскаяобласть", "Гродненская область"),
    ("городМинск", "г. Минск"),
    ("Минскаяобласть", "Минская область"),
    ("Могилёвскаяобласть", "Могилевская область"),
    ("Общийитог", "Всего по республике"),
]
NUM_RE = re.compile(r"\d+,\d{3}")


def rtf_to_text(raw_bytes):
    s = raw_bytes.decode("cp1251", errors="ignore")

    def uni(m):
        n = int(m.group(1))
        return chr(n + 65536 if n < 0 else n)

    s = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1251"), s)
    s = re.sub(r"\\u(-?[0-9]+)\s?", uni, s)
    # границы ячеек/строк -> разделители ДО удаления прочих управляющих слов
    s = s.replace("\\cell", "\t").replace("\\tab", "\t")
    s = re.sub(r"\\(row|par)\b", "\n", s)
    # отбрасываем встроенные объекты (бинарный хвост)
    s = re.split(r"\\object|\\objdata", s)[0]
    s = re.sub(r"\\[a-zA-Z]+-?[0-9]*[ ]?", "", s)
    s = re.sub(r"[{}]", "", s)
    return s


def main():
    text = rtf_to_text(SRC.read_bytes())
    lines = text.split("\n")

    # находим строки, где ЗАВЕРШАЕТСЯ имя региона (имена порваны посреди слова)
    completions = []  # (line_index, region)
    letters = ""
    for i, line in enumerate(lines):
        letters += re.sub(r"[^A-Za-zА-Яа-яЁё]", "", line)
        flat = letters.replace(" ", "")
        for key, name in REGION_KEYS:
            if key in flat:
                completions.append((i, name))
                letters = ""
                break

    rows = []
    for j, (i, region) in enumerate(completions):
        end = completions[j + 1][0] if j + 1 < len(completions) else len(lines)
        nums = []
        for line in lines[i:end]:
            nums += [float(m.replace(",", ".")) for m in NUM_RE.findall(line)]
        if len(nums) != 9:
            print(f"ПРЕДУПРЕЖДЕНИЕ {region}: найдено чисел {len(nums)} вместо 9: {nums}")
            continue
        # валидация: удалено-всего == сумма четырёх «из них»
        sub = sum(nums[4:8])
        if abs(sub - nums[3]) > 0.05:
            print(f"ПРЕДУПРЕЖДЕНИЕ {region}: сумма подытогов {sub:.3f} != удалено {nums[3]:.3f}")
        for col, val in zip(COLUMNS, nums):
            rows.append({"region": region, "indicator": col, "year": 2025,
                         "value": val, "unit": "1000 т",
                         "source_file": SRC.name, "source_note": "таблица по областям"})

    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["region", "indicator", "year", "value", "unit",
                                          "source_file", "source_note"])
        w.writeheader()
        w.writerows(rows)

    regions = sorted({r["region"] for r in rows})
    print(f"строк: {len(rows)}, регионов: {len(regions)} -> {DST.name}")
    for reg in regions:
        gen = next(r["value"] for r in rows if r["region"] == reg and r["indicator"] == "Образовано")
        print(f"   {reg}: Образовано = {gen} тыс. т")


if __name__ == "__main__":
    sys.exit(main())
