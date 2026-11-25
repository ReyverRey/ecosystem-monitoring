"""Модели прогноза качества воздуха (Этап 5 по ТЗ, п. 4.3).

Серии: все пары «город × загрязнитель» с >= 8 годами наблюдений.
Модели: naive (последний год), линейный тренд, Тейл-Сен, Холт, панельный LightGBM (лаги + вода/отходы).
Валидация: расширяющееся окно, горизонты h=1..3, отложенные годы (без перемешивания).
Метрики: MAE, RMSE, sMAPE. Финальный прогноз 2026-2028 с бутстрэп-интервалами по остаткам.

Выходы: reports/model_metrics.md, reports/figures/*.png, data/processed/forecast_2026_2028.csv
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.holtwinters import Holt
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
FIG = ROOT / "reports" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

HORIZONS = [1, 2, 3]
LAST_YEAR = 2025
FINAL_YEARS = [2026, 2027, 2028]
BOOTSTRAP_N = 1000
RNG = np.random.default_rng(42)

out = []


def log(s=""):
    print(s)
    out.append(str(s))


def load(name):
    df = pd.read_csv(PROC / name)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


air = load("air_belstat_tidy.csv")
waste = load("I1-2005-2025_tidy.csv")
w_res = load("C1-1990-2024_tidy.csv")
w_dis = load("C16-2005-2025_tidy.csv")

conc = air[air["indicator"].str.startswith("Среднегодовая концентрация")]
conc = conc.groupby(["city", "pollutant", "year"], as_index=False)["value"].mean()
conc = conc.dropna(subset=["value"])

counts = conc.groupby(["city", "pollutant"])["year"].count()
series_ids = counts[counts >= 8].index
conc = conc.set_index(["city", "pollutant"]).loc[series_ids].reset_index()

ext = pd.DataFrame({"year": range(1990, LAST_YEAR + 1)})
for name, df_, col in [("waste_total", waste, "Всего образовано отходов производства"),
                       ("wastewater", w_dis, "Сброс сточных вод в поверхностные водные объекты"),
                       ("water_resources", w_res, None)]:
    if col is None:
        s = df_[df_["indicator"].str.startswith("Возобновляемые ресурсы")]
    else:
        s = df_[df_["indicator"] == col]
    ext = ext.merge(s[["year", "value"]].rename(columns={"value": name}), on="year", how="left")


def series_values(city, pol):
    s = conc[(conc["city"] == city) & (conc["pollutant"] == pol)].set_index("year")["value"]
    return s.sort_index()


def sMAPE(y, yhat):
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    denom = np.abs(y) + np.abs(yhat)
    return float(np.mean(200.0 * np.abs(y - yhat) / np.where(denom == 0, 1e-9, denom)))


# ---------- подготовка панельных признаков ----------
panel = conc.copy().sort_values(["city", "pollutant", "year"])
grp = panel.groupby(["city", "pollutant"])["value"]
for lag in (1, 2, 3):
    panel[f"lag{lag}"] = grp.shift(lag)
panel["mean3"] = grp.transform(lambda s: s.rolling(3, min_periods=1).mean())
panel = panel.merge(ext, on="year", how="left")
for name in ("waste_total", "wastewater", "water_resources"):
    panel[f"{name}_lag1"] = panel.groupby(["city", "pollutant"])[name].shift(1)
panel["city_id"] = panel.groupby("city").ngroup()
panel["pol_id"] = panel.groupby("pollutant").ngroup()

FEATURES = ["city_id", "pol_id", "lag1", "lag2", "lag3", "mean3",
            "waste_total_lag1", "wastewater_lag1", "water_resources_lag1"]

origins = list(range(2013, LAST_YEAR))
records = []


def preds_from_models(city, pol, origin, h):
    s = series_values(city, pol)
    hist = s[s.index <= origin]
    outp = {}
    y = hist.values
    x = hist.index.values.astype(float)
    if len(hist) < 3 or origin not in hist.index:
        return None
    outp["naive"] = float(hist.iloc[-1])
    k, b = np.polyfit(x, y, 1)
    outp["lin_trend"] = float(k * (origin + h) + b)
    slope, intercept, _, _ = stats.theilslopes(y, x)
    outp["theilsen"] = float(slope * (origin + h) + intercept)
    try:
        fit = Holt(hist.values, initialization_method="estimated").fit()
        outp["holt"] = float(fit.forecast(h)[-1])
    except Exception:
        outp["holt"] = outp["naive"]
    return outp


def panel_pred(train_df, row, h, origin):
    """Прогноз панельной моделью: train — все ряды с target <= origin."""
    df_h = train_df.copy()
    df_h["target"] = df_h.groupby(["city", "pollutant"])["value"].shift(-h)
    df_h = df_h.dropna(subset=["target"] + FEATURES)
    if len(df_h) < 100:
        return None
    model = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05,
                              num_leaves=15, min_child_samples=10, verbose=-1)
    model.fit(df_h[FEATURES], df_h["target"])
    return float(model.predict(pd.DataFrame([row[FEATURES]]))[0])


log(f"Серий в модели: {panel.groupby(['city', 'pollutant']).ngroups}; "
    f"строк панели: {len(panel)}\n")

for origin in origins:
    for h in HORIZONS:
        if origin + h > LAST_YEAR:
            continue
        train_df = panel[panel["year"] <= origin]
        for _, row in panel[panel["year"] == origin].iterrows():
            truth = series_values(row["city"], row["pollutant"]).get(origin + h, np.nan)
            if np.isnan(truth):
                continue
            base = preds_from_models(row["city"], row["pollutant"], origin, h)
            if base is None:
                continue
            for name, yhat in base.items():
                records.append({"city": row["city"], "pollutant": row["pollutant"],
                                "origin": origin, "horizon": h, "year": origin + h,
                                "model": name, "y_true": truth, "y_pred": yhat})
            yhat = panel_pred(train_df, row, h, origin)
            if yhat is not None:
                records.append({"city": row["city"], "pollutant": row["pollutant"],
                                "origin": origin, "horizon": h, "year": origin + h,
                                "model": "panel_lgb", "y_true": truth, "y_pred": yhat})

bt = pd.DataFrame(records)
bt.to_csv(PROC / "backtest_results.csv", index=False)

# ---------- метрики ----------
log("## Метрики бэктеста по горизонтам (усреднение по сериям и годам)\n")
rows = []
for (model, h), g in bt.groupby(["model", "horizon"]):
    mae = np.mean(np.abs(g["y_true"] - g["y_pred"]))
    rmse = np.sqrt(np.mean((g["y_true"] - g["y_pred"]) ** 2))
    rows.append({"model": model, "horizon": h, "n": len(g),
                 "MAE": round(mae, 2), "RMSE": round(rmse, 2),
                 "sMAPE%": round(sMAPE(g["y_true"], g["y_pred"]), 1)})
metrics = pd.DataFrame(rows).sort_values(["horizon", "MAE"])
log(metrics.to_string(index=False))
log()

log("## Лучшая модель по MAE на каждом горизонте\n")
best = metrics.loc[metrics.groupby("horizon")["MAE"].idxmin()]
log(best[["horizon", "model", "MAE", "RMSE", "sMAPE%"]].to_string(index=False))
log()

log("## Те же метрики отдельно по CO и NO2 (ядро данных)\n")
core = bt[bt["pollutant"].isin(["CO", "NO2"])]
rows = []
for (model, h), g in core.groupby(["model", "horizon"]):
    rows.append({"model": model, "horizon": h, "n": len(g),
                 "MAE": round(np.mean(np.abs(g["y_true"] - g["y_pred"])), 2),
                 "sMAPE%": round(sMAPE(g["y_true"], g["y_pred"]), 1)})
log(pd.DataFrame(rows).sort_values(["horizon", "MAE"]).to_string(index=False))
log()

# график метрик
fig, ax = plt.subplots(figsize=(9, 5))
for model in sorted(bt["model"].unique()):
    s = metrics[metrics["model"] == model]
    ax.plot(s["horizon"], s["MAE"], marker="o", label=model)
ax.set_title("MAE по горизонтам прогноза")
ax.set_xlabel("Горизонт, лет")
ax.set_ylabel("MAE")
ax.set_xticks(HORIZONS)
ax.grid(alpha=0.3)
ax.legend()
fig.tight_layout()
fig.savefig(FIG / "model_metrics_by_horizon.png")
plt.close(fig)

# ---------- финальный прогноз 2026-2028 ----------
best_model = {int(r["horizon"]): r["model"] for _, r in best.iterrows()}
fc_rows = []
resid_by_h = {h: (bt[(bt["model"] == best_model[h]) & (bt["horizon"] == h)]["y_true"]
                  - bt[(bt["model"] == best_model[h]) & (bt["horizon"] == h)]["y_pred"]).values
              for h in HORIZONS}

for (city, pol), s in conc.groupby(["city", "pollutant"]):
    s = s.set_index("year")["value"].sort_index()
    for h in HORIZONS:
        target_year = LAST_YEAR + h
        model = best_model[h]
        if model == "panel_lgb":
            row = panel[(panel["city"] == city) & (panel["pollutant"] == pol)
                        & (panel["year"] == LAST_YEAR)]
            train_df = panel[panel["year"] <= LAST_YEAR]
            yhat = panel_pred(train_df, row.iloc[0], h, LAST_YEAR) if len(row) else None
        else:
            pred = preds_from_models(city, pol, LAST_YEAR, h)
            yhat = pred[model] if pred else None
        if yhat is None:
            continue
        res = resid_by_h[h]
        boots = yhat + RNG.choice(res, size=(BOOTSTRAP_N,), replace=True) if len(res) else np.array([yhat])
        lo, hi = np.percentile(boots, [2.5, 97.5])
        fc_rows.append({"city": city, "pollutant": pol, "year": target_year,
                        "model": model, "forecast": round(yhat, 2),
                        "lo_95": round(float(lo), 2), "hi_95": round(float(hi), 2)})

fc = pd.DataFrame(fc_rows)
fc.to_csv(PROC / "forecast_2026_2028.csv", index=False)
log(f"## Финальный прогноз 2026-2028: {len(fc)} записей -> data/processed/forecast_2026_2028.csv")
log(fc[fc["pollutant"] == "CO"].head(12).to_string(index=False))
log()

# примеры прогноза
fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
for ax, (city, pol) in zip(axes, [("Минск", "CO"), ("Гомель", "CO"), ("Минск", "NO2")]):
    s = conc[(conc["city"] == city) & (conc["pollutant"] == pol)].set_index("year")["value"].sort_index()
    f = fc[(fc["city"] == city) & (fc["pollutant"] == pol)].sort_values("year")
    ax.plot(s.index, s.values, "-o", ms=3, label="факт")
    ax.plot(f["year"], f["forecast"], "-s", ms=4, color="tab:red", label="прогноз")
    ax.fill_between(f["year"], f["lo_95"], f["hi_95"], color="tab:red", alpha=0.2, label="95% интервал")
    ax.set_title(f"{city}, {pol}")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(FIG / "forecast_examples.png")
plt.close(fig)

(ROOT / "reports" / "model_metrics.md").write_text("\n".join(out), encoding="utf-8")
print(f"figures -> {FIG}")
print(f"metrics -> {ROOT / 'reports' / 'model_metrics.md'}")
