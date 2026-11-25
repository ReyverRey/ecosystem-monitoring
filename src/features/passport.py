"""Экопаспорт региона: сводка воздуха, воды и отходов в один индекс.

Вход:  data/processed/air_belstat_tidy.csv        (город x загрязнитель x год, есть ПДК)
       data/processed/water_regions_tidy.csv      (сброс вод по областям, 2021-2025, API Белстата)
       data/processed/waste_regions_2025_tidy.csv (отходы по областям, 2025, Минприроды)
Выход: data/processed/passport_regions.csv

Методика (описывается в пояснительной записке):
- блок «воздух»: среднее отношение «среднегодовая концентрация / среднегодовая ПДК»
  по городам региона за последние 5 лет (меньше — лучше);
- блок «вода»: средний сброс вод за 2021-2025, млн м3/год (меньше — лучше);
  пересчёт на душу населения не выполняется: региональные данные о численности
  не входят в выбранные источники (ограничение, выносится в записку);
- блок «отходы»: образование отходов производства в 2025, тыс. т (меньше — лучше);
- нормировка min-max по 8 регионам: score = 100 * (max - x) / (max - min),
  100 — лучшее значение среди регионов;
- индекс = взвешенная сумма баллов доступных блоков (веса настраиваются);
- «что если»: значение блока умножается на коэффициент, индекс пересчитывается
  с теми же границами нормировки — сценарная оценка, не прогноз.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
DST = PROC / "passport_regions.csv"

LAST_YEARS = 5
CITY_TO_REGION = {
    "Брест": "Брестская область", "Пинск": "Брестская область",
    "Витебск": "Витебская область", "Новополоцк": "Витебская область",
    "Орша": "Витебская область", "Полоцк": "Витебская область",
    "Гомель": "Гомельская область", "Светлогорск": "Гомельская область",
    "Гродно": "Гродненская область",
    "Минск": "г. Минск",
    "Бобруйск": "Могилевская область", "Могилев": "Могилевская область",
}
REGIONS = ["Брестская область", "Витебская область", "Гомельская область",
           "Гродненская область", "г. Минск", "Минская область",
           "Могилевская область"]
BLOCKS = ["air", "water", "waste"]


def load_blocks():
    air = pd.read_csv(PROC / "air_belstat_tidy.csv")
    air["value"] = pd.to_numeric(air["value"], errors="coerce")
    conc = air[air["indicator"].str.startswith("Среднегодовая концентрация")]
    pdk = air[air["indicator"].str.startswith("Среднегодовое значение ПДК")][
        ["city", "pollutant", "year", "value"]].rename(columns={"value": "pdk"})
    merged = conc.merge(pdk, on=["city", "pollutant", "year"], how="left")
    merged = merged.dropna(subset=["value", "pdk"])
    merged["ratio"] = merged["value"] / merged["pdk"]
    merged["region"] = merged["city"].map(CITY_TO_REGION)
    merged = merged[merged["year"] >= merged["year"].max() - LAST_YEARS + 1]
    air_block = merged.groupby("region")["ratio"].mean().rename("air_ratio")

    water = pd.read_csv(PROC / "water_regions_tidy.csv")
    water["value"] = pd.to_numeric(water["value"], errors="coerce")
    water_block = water.groupby("region")["value"].mean().rename("water_discharge")

    waste = pd.read_csv(PROC / "waste_regions_2025_tidy.csv")
    waste["value"] = pd.to_numeric(waste["value"], errors="coerce")
    wgen = waste[waste["indicator"] == "Образовано"]
    waste_block = wgen.set_index("region")["value"].rename("waste_generated")

    return air_block, water_block, waste_block


def norm_score(series):
    """100 — лучшее (минимальное) значение, 0 — худшее."""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(50.0, index=series.index)
    return 100.0 * (hi - series) / (hi - lo)


def build():
    air_block, water_block, waste_block = load_blocks()
    df = pd.DataFrame(index=REGIONS)
    df.index.name = "region"
    df["air_ratio"] = air_block
    df["water_discharge"] = water_block
    df["waste_generated"] = waste_block
    for col, block in [("air_ratio", "air_score"), ("water_discharge", "water_score"),
                       ("waste_generated", "waste_score")]:
        df[block] = norm_score(df[col])
    df["index_equal_weights"] = df[["air_score", "water_score", "waste_score"]].mean(axis=1)
    return df.reset_index()


def score_with(df, weights, multipliers=None):
    """Сценарий: multipliers = {'air': k, 'water': k, 'waste': k} к исходным значениям."""
    multipliers = multipliers or {}
    cols = {"air": ("air_ratio", "air_score"), "water": ("water_discharge", "water_score"),
            "waste": ("waste_generated", "waste_score")}
    out = pd.DataFrame({"region": df["region"]})
    for block, (raw_col, score_col) in cols.items():
        raw = df[raw_col] * multipliers.get(block, 1.0)
        lo, hi = df[raw_col].min(), df[raw_col].max()
        out[score_col] = 100.0 * (hi - raw) / (hi - lo) if hi != lo else 50.0
    wsum = sum(weights[b] for b in BLOCKS)
    score_cols = [cols[b][1] for b in BLOCKS]
    w = pd.Series({cols[b][1]: weights[b] for b in BLOCKS})
    valid = out[score_cols].notna()
    num = (out[score_cols].fillna(0) * w).sum(axis=1)
    den = (valid * w).sum(axis=1).replace(0, 1)  # NaN-блоки не входят в знаменатель
    out["index"] = num / den
    return out


def main():
    df = build()
    df.to_csv(DST, index=False)
    print(df.round(1).to_string(index=False))
    print(f"\n-> {DST}")


if __name__ == "__main__":
    sys.exit(main())
