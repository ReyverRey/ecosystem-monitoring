"""EDA по данным Белстата: воздух (A2), отходы (I1), вода (C1/C16).

Вход:  data/processed/*_tidy.csv
Выход: reports/figures/*.png, reports/eda_tables.md

Разделы:
1. Покрытие данных по городам и загрязнителям.
2. Динамика среднегодовых концентраций по городам (графики).
3. Тренды Тейла–Сена по городам и загрязнителям (наклон, 95% CI).
4. Аномалия 2020 года (изменение к 2019).
5. Связи «воздух ↔ вода ↔ отходы» на национальном уровне (Пирсон/Спирмен).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
FIG = ROOT / "reports" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["figure.dpi"] = 110

out = []


def log(s=""):
    print(s)
    out.append(s)


def load(name):
    df = pd.read_csv(PROC / name)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


air = load("air_belstat_tidy.csv")
waste = load("I1-2005-2025_tidy.csv")
w_res = load("C1-1990-2024_tidy.csv")
w_dis = load("C16-2005-2025_tidy.csv")

conc = air[air["indicator"].str.startswith("Среднегодовая концентрация")].copy()
# для городов с зонами (жилой/промышленный район) усредняем по зонам
conc = conc.groupby(["city", "pollutant", "year"], as_index=False)["value"].mean()

# ---------- 1. Покрытие ----------
log("## 1. Покрытие: число городов с данными по загрязнителю и годам\n")
piv = conc.dropna(subset=["value"]).pivot_table(
    index="pollutant", columns="city", values="year", aggfunc="count", fill_value=0
)
log(piv.to_string())
log()

# ---------- 2. Динамика по городам ----------
colors = plt.cm.tab20(np.linspace(0, 1, 12))
for pol in ["PM10", "NO2", "SO2", "CO", "O3"]:
    sub = conc[conc["pollutant"] == pol].dropna(subset=["value"])
    if sub.empty:
        continue
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, (city, g) in enumerate(sub.groupby("city")):
        g = g.sort_values("year")
        ax.plot(g["year"], g["value"], marker="o", ms=3, lw=1.2, color=colors[i % 12], label=city)
    unit = air.loc[air["pollutant"] == pol, "unit"].iloc[0]
    ax.set_title(f"Среднегодовая концентрация {pol} по городам, {unit}")
    ax.set_xlabel("Год")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7, ncol=4, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / f"air_{pol}_by_city.png")
    plt.close(fig)

# сводный график средних по загрязнителям (без CO — другая единица)
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for ax, pols, title in [
    (axes[0], ["PM10", "NO2", "SO2", "O3"], "мкг/м3"),
    (axes[1], ["CO"], "мг/м3"),
]:
    for pol in pols:
        s = conc[conc["pollutant"] == pol].dropna(subset=["value"])
        nat = s.groupby("year")["value"].mean()
        ax.plot(nat.index, nat.values, marker="o", ms=3, label=pol)
    ax.set_title(f"Среднее по 12 городам ({title})")
    ax.set_xlabel("Год")
    ax.grid(alpha=0.3)
    ax.legend()
fig.tight_layout()
fig.savefig(FIG / "air_national_mean.png")
plt.close(fig)

# ---------- 3. Тренды Тейла–Сена ----------
log("## 3. Тренды Тейла–Сена (склон в единицах измерения в год, 95% CI)\n")
rows = []
for (city, pol), g in conc.dropna(subset=["value"]).groupby(["city", "pollutant"]):
    g = g.sort_values("year")
    if len(g) >= 8:
        slope, intercept, lo, up = stats.theilslopes(g["value"], g["year"])
        sig = "да" if (lo > 0 or up < 0) else "нет"
        rows.append({"city": city, "pollutant": pol, "n_years": len(g),
                     "slope": round(slope, 3), "ci_low": round(lo, 3),
                     "ci_high": round(up, 3), "significant": sig})
trends = pd.DataFrame(rows).sort_values(["pollutant", "city"])
log(trends.to_string(index=False))
log()

# ---------- 4. Аномалия 2020 ----------
log("## 4. Изменение 2020 к 2019, % (среднегодовая концентрация)\n")
p19 = conc[conc["year"] == 2019].set_index(["city", "pollutant"])["value"]
p20 = conc[conc["year"] == 2020].set_index(["city", "pollutant"])["value"]
delta = ((p20 - p19) / p19 * 100).dropna().rename("pct_2020_vs_2019").round(1)
log(delta.to_string())
log()
dplot = delta.reset_index()
fig, ax = plt.subplots(figsize=(10, 5))
for pol in sorted(dplot["pollutant"].unique()):
    s = dplot[dplot["pollutant"] == pol]
    ax.plot(s["city"], s["pct_2020_vs_2019"], marker="o", ls="", ms=6, label=pol)
ax.axhline(0, color="black", lw=0.8)
ax.set_title("Изменение среднегодовых концентраций 2020 к 2019, %")
ax.grid(alpha=0.3)
ax.tick_params(axis="x", rotation=45)
ax.legend()
fig.tight_layout()
fig.savefig(FIG / "air_anomaly_2020.png")
plt.close(fig)

# ---------- 5. Воздух ↔ вода ↔ отходы ----------
log("## 5. Национальные ряды и корреляции (воздух ↔ вода ↔ отходы)\n")
nat_air = conc.dropna(subset=["value"]).groupby(["pollutant", "year"])["value"].mean().unstack(0)
waste_total = waste[waste["indicator"] == "Всего образовано отходов производства"][
    ["year", "value"]].rename(columns={"value": "waste_total"}).set_index("year")
wastewater = w_dis[w_dis["indicator"] == "Сброс сточных вод в поверхностные водные объекты"][
    ["year", "value"]].rename(columns={"value": "wastewater"}).set_index("year")
res = w_res[w_res["indicator"].str.startswith("Возобновляемые ресурсы")][
    ["year", "value"]].rename(columns={"value": "water_resources"}).set_index("year")

nat = nat_air.join(waste_total).join(wastewater).join(res)
log(nat.round(1).to_string())
log()

log("Корреляции Пирсона / Спирмена (число общих годов в скобках; осторожно: ряды короткие)\n")
pairs = [("PM10", "waste_total"), ("PM10", "wastewater"), ("PM10", "water_resources"),
         ("CO", "waste_total"), ("NO2", "waste_total"), ("NO2", "wastewater")]
for a, b in pairs:
    s = nat[[a, b]].dropna()
    if len(s) >= 8:
        pr = stats.pearsonr(s[a], s[b])
        sr = stats.spearmanr(s[a], s[b])
        log(f"- {a} vs {b}: r={pr[0]:.2f} (p={pr[1]:.3f}), rho={sr[0]:.2f} (p={sr[1]:.3f}), n={len(s)}")
log()

fig, ax = plt.subplots(figsize=(10, 5))
base = nat.index.min()
for col, style in [("PM10", "-o"), ("waste_total", "-s"), ("wastewater", "-^"), ("water_resources", "-d")]:
    s = nat[col].dropna()
    ax.plot(s.index, s / s.iloc[0] * 100, style, ms=4, lw=1.3, label=col)
ax.axhline(100, color="black", lw=0.8)
ax.set_title("Национальные ряды, индекс (первый общий год = 100)")
ax.set_xlabel("Год")
ax.grid(alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig(FIG / "national_index.png")
plt.close(fig)

(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports" / "eda_tables.md").write_text("\n".join(out), encoding="utf-8")
print(f"\nfigures -> {FIG}")
print(f"tables  -> {ROOT / 'reports' / 'eda_tables.md'}")
