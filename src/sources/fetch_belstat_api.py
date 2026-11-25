"""Загрузка региональных данных из API dataportal.belstat.gov.by (SDMX-JSON).

Показатели:
- 10301000009 «Сброс вод» (млн м3) — по территориям, 2021-2025;
- 10301000011 «Образование отходов производства» (тыс. т) — по территориям, 2021-2025.

Особенности API:
- год запрашивается по одному (мульти-запрос возвращает одно значение);
- ключи наблюдений — индексы в порядке СОБСТВЕННОЙ структуры ответа
  (structure.dimensions.observation), коды регионов берутся оттуда, а не из запроса.

Выход: data/raw/dataportal/*.json (сырое),
       data/processed/water_regions_tidy.csv, data/processed/waste_regions_tidy.csv
"""
import csv
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "dataportal"
PROC = ROOT / "data" / "processed"
RAW.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)

BASE = "https://dataportal.belstat.gov.by/osids-public-api/sdmx-api/indicator"
YEARS = [2021, 2022, 2023, 2024, 2025]
REGION_CODES = ["699961", "919067", "919068", "919069", "919070", "919071", "919072", "919073"]
RU_NAMES = {
    "699961": "Республика Беларусь", "919067": "Брестская область",
    "919068": "Витебская область", "919069": "Гомельская область",
    "919070": "Гродненская область", "919071": "г. Минск",
    "919072": "Минская область", "919073": "Могилевская область",
}

INDICATORS = {
    "10301000009": {
        "label": "Сброс вод", "unit": "млн м3/год", "unit_code": "274",
        "dims": ["razrez_594", "priznak_10261"],
        "params": {"razrez_594": REGION_CODES, "priznak_10261": ["2"]},
        "out": "water_regions_tidy.csv",
    },
    "10301000011": {
        "label": "Образование отходов производства", "unit": "1000 т/год", "unit_code": "119",
        "dims": ["razrez_594", "priznak_10261", "priznak_10755", "priznak_10756"],
        "params": {"razrez_594": REGION_CODES, "priznak_10261": ["2"],
                   "priznak_10755": ["2"], "priznak_10756": ["2"]},
        "out": "waste_regions_tidy.csv",
    },
}


def api_post(indicator_id, spec, year):
    payload = {
        "years": [year], "periodicities": [], "units": [spec["unit_code"]],
        "dimensionOrder": spec["dims"], "dimensionParams": spec["params"],
        "simbolsAfterComma": 3,
    }
    req = urllib.request.Request(
        f"{BASE}/values/SDMX-JSON/{indicator_id}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def decode(resp):
    """(регион, значение) из наблюдений по СОБСТВЕННОЙ структуре ответа."""
    dims = sorted(resp["structure"]["dimensions"]["observation"],
                  key=lambda d: d.get("keyPosition", 0))
    region_dim = next((d for d in dims if d["id"] == "razrez_594"), None)
    obs = resp["dataSets"][0].get("observations", {})
    out = []
    for key, val in obs.items():
        idx = [int(p) for p in key.split(":")]
        region = ""
        if region_dim is not None:
            pos = region_dim.get("keyPosition", 0)
            if idx[pos] < len(region_dim["values"]):
                code = region_dim["values"][idx[pos]].get("id", "")
                region = RU_NAMES.get(code, region_dim["values"][idx[pos]].get("name", ""))
        v = val[0] if isinstance(val, list) else val
        try:
            out.append((region, float(v)))
        except (TypeError, ValueError):
            continue
    return out


def main():
    for indicator_id, spec in INDICATORS.items():
        rows = []
        for year in YEARS:
            resp = api_post(indicator_id, spec, year)
            (RAW / f"{indicator_id}_{year}.json").write_text(
                json.dumps(resp, ensure_ascii=False), encoding="utf-8")
            for region, value in decode(resp):
                rows.append({"indicator": spec["label"], "region": region,
                             "year": year, "value": value, "unit": spec["unit"],
                             "source": f"dataportal:{indicator_id}"})
        dst = PROC / spec["out"]
        with open(dst, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["indicator", "region", "year", "value", "unit", "source"])
            w.writeheader()
            w.writerows(rows)
        print(f"{indicator_id} {spec['label']}: {len(rows)} строк -> {dst.name}")
        by_region = {}
        for r in rows:
            by_region.setdefault(r["region"], []).append((r["year"], r["value"]))
        for reg in sorted(by_region):
            print(f"   {reg}: " + ", ".join(f"{y}={v}" for y, v in sorted(by_region[reg])))


if __name__ == "__main__":
    main()
