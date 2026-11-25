"""Дашборд «Мониторинг экосистемы»: качество воздуха по городам Беларуси.

Запуск:  streamlit run app/app.py
Страницы: Обзор, Машина времени, Динамика и сравнение, Прогноз, О данных.
Данные: data/processed/*.csv (offline, без внешних API — по ТЗ).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

st.set_page_config(page_title="Мониторинг экосистемы", page_icon="🌿", layout="wide")

CITY_COORDS = {
    "Минск": (53.90, 27.57), "Гомель": (52.43, 30.98), "Могилев": (53.91, 30.34),
    "Брест": (52.10, 23.69), "Витебск": (55.19, 30.20), "Гродно": (53.68, 23.83),
    "Бобруйск": (53.13, 29.23), "Новополоцк": (55.53, 28.66), "Орша": (54.51, 30.42),
    "Пинск": (52.11, 26.10), "Полоцк": (55.49, 28.77), "Светлогорск": (52.63, 29.73),
}
POLLUTANT_LABELS = {"CO": "CO (оксид углерода)", "NO2": "NO₂ (диоксид азота)",
                    "SO2": "SO₂ (диоксид серы)", "PM10": "PM₁₀ (твёрдые частицы)",
                    "O3": "O₃ (озон)"}


@st.cache_data
def load_air():
    df = pd.read_csv(PROC / "air_belstat_tidy.csv")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    conc = df[df["indicator"].str.startswith("Среднегодовая концентрация")]
    conc = conc.groupby(["city", "pollutant", "year"], as_index=False)["value"].mean()
    conc = conc.dropna(subset=["value"])
    conc["lat"] = conc["city"].map(lambda c: CITY_COORDS.get(c, (np.nan, np.nan))[0])
    conc["lon"] = conc["city"].map(lambda c: CITY_COORDS.get(c, (np.nan, np.nan))[1])
    return conc


@st.cache_data
def load_forecast():
    path = PROC / "forecast_2026_2028.csv"
    return pd.read_csv(path) if path.exists() else None


@st.cache_data
def load_backtest():
    path = PROC / "backtest_results.csv"
    return pd.read_csv(path) if path.exists() else None


air = load_air()
fc = load_forecast()
bt = load_backtest()

st.title("Мониторинг и прогноз качества воздуха по городам Беларуси")
page = st.sidebar.radio("Навигация", ["Обзор", "Машина времени", "Динамика и сравнение",
                                      "Прогноз", "О данных"])
pol = st.sidebar.selectbox("Загрязняющее вещество", sorted(air["pollutant"].unique()),
                           format_func=lambda p: POLLUTANT_LABELS.get(p, p))

if page == "Обзор":
    year = st.slider("Год", int(air["year"].min()), int(air["year"].max()),
                     int(air["year"].max()))
    sub = air[(air["pollutant"] == pol) & (air["year"] == year)]
    if sub.empty:
        st.warning(f"За {year} год данных по {pol} нет")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Городов с данными", len(sub))
        c2.metric("Среднее по городам", f"{sub['value'].mean():.1f}")
        worst = sub.loc[sub["value"].idxmax()]
        c3.metric("Максимум", f"{worst['value']:.1f} ({worst['city']})")
        fig = px.scatter_map(sub, lat="lat", lon="lon", color="value", size="value",
                             size_max=28, hover_name="city",
                             hover_data={"value": ":.1f", "lat": False, "lon": False},
                             color_continuous_scale="RdYlGn_r", zoom=4.6,
                             center={"lat": 53.5, "lon": 28.0}, map_style="open-street-map",
                             labels={"value": "концентрация"},
                             title=f"{POLLUTANT_LABELS[pol]}, {year} год")
        fig.update_layout(height=560, margin=dict(l=0, r=0))
        st.plotly_chart(fig, width='stretch')
        st.caption("Данные: Белстат SEIS (A2), среднегодовые концентрации; "
                   "для городов с зонами наблюдения — среднее по зонам.")

elif page == "Машина времени":
    years = sorted(air.loc[air["pollutant"] == pol, "year"].unique())
    sub = air[air["pollutant"] == pol]
    fig = px.scatter_map(sub, lat="lat", lon="lon", color="value", size="value",
                         size_max=28, animation_frame="year", hover_name="city",
                         color_continuous_scale="RdYlGn_r", zoom=4.6,
                         center={"lat": 53.5, "lon": 28.0}, map_style="open-street-map",
                         range_color=[sub["value"].min(), sub["value"].max()],
                         labels={"value": "концентрация"},
                         title=f"Динамика {POLLUTANT_LABELS[pol]} по годам")
    fig.update_layout(height=620, margin=dict(l=0, r=0))
    st.plotly_chart(fig, width='stretch')
    st.caption("Используйте кнопку воспроизведения под картой. "
               "Годы без наблюдений пропускаются.")

elif page == "Динамика и сравнение":
    cities = st.multiselect("Города", sorted(air["city"].unique()),
                            default=sorted(air["city"].unique())[:6])
    y0, y1 = st.select_slider("Период", options=sorted(air["year"].unique()),
                              value=(int(air["year"].min()), int(air["year"].max())))
    sub = air[(air["pollutant"] == pol) & (air["city"].isin(cities))
              & (air["year"].between(y0, y1))]
    st.plotly_chart(px.line(sub, x="year", y="value", color="city", markers=True,
                            labels={"year": "Год", "value": "концентрация", "city": "Город"},
                            title=f"{POLLUTANT_LABELS[pol]}, {y0}–{y1}"),
                    width='stretch')
    rank = (sub.groupby("city")["value"].agg(["mean", "min", "max", "count"])
            .sort_values("mean", ascending=False)
            .rename(columns={"mean": "среднее", "min": "минимум", "max": "максимум",
                             "count": "лет данных"}))
    st.subheader("Рейтинг городов по среднему уровню")
    st.dataframe(rank.round(1), width='stretch')

elif page == "Прогноз":
    if fc is None or bt is None:
        st.warning("Модели ещё не обучены: запустите `python src/models/train_forecast.py`")
    else:
        city = st.selectbox("Город", sorted(air["city"].unique()))
        s = air[(air["city"] == city) & (air["pollutant"] == pol)]
        f = fc[(fc["city"] == city) & (fc["pollutant"] == pol)]
        fig = px.line(s, x="year", y="value", markers=True,
                      labels={"year": "Год", "value": "концентрация"},
                      title=f"{city}: факт и прогноз {POLLUTANT_LABELS[pol]}")
        if not f.empty:
            fig.add_scatter(x=f["year"], y=f["forecast"], mode="lines+markers",
                            name="прогноз", line=dict(color="red", dash="dash"))
            fig.add_scatter(x=f["year"], y=f["hi_95"], mode="lines",
                            line=dict(width=0), showlegend=False)
            fig.add_scatter(x=f["year"], y=f["lo_95"], mode="lines",
                            fill="tonexty", line=dict(width=0), fillcolor="rgba(255,0,0,0.15)",
                            name="95% интервал")
        st.plotly_chart(fig, width='stretch')

        st.subheader("Качество моделей (бэктест на отложенных годах)")
        m = (bt.assign(err=(bt["y_true"] - bt["y_pred"]).abs())
             .groupby(["model", "horizon"])["err"].mean().unstack()
             .rename(columns={h: f"MAE h={h}" for h in sorted(bt["horizon"].unique())}))
        st.dataframe(m.round(2), width='stretch')
        st.caption("Меньше — лучше. Прогноз подписан как оценка тренда; "
                   "интервал построен бутстрэпом остатков бэктеста.")

else:  # О данных
    st.markdown("""
**Источники данных (оффлайн, лежат в `data/`):**

- **Воздух** — Белстат, Совместная система экологической информации, индикатор A.2
  «Качество атмосферного воздуха в городских населённых пунктах», xlsx 2005–2025:
  среднегодовые концентрации CO, NO₂, SO₂, PM₁₀, O₃ по 12 городам.
- **Отходы** — Белстат I.1 «Образование отходов», xlsx 2005–2025.
- **Вода** — Белстат C.1 (водные ресурсы), C.3 (водопользование), C.16 (сточные воды), C.11 (биогены).

**Методика:** значения извлекаются скриптами `src/clean/` без ручных правок,
каждая строка датасета хранит файл-источник и лист. Прогноз строится моделями
`src/models/train_forecast.py` (наивный, линейный тренд, Тейл–Сен, Холт, панельный
LightGBM) с валидацией расширяющимся окном на отложенных годах.

**Ограничения:** годовые ряды (около 21 точки на серию) — прогноз 1–3 года интерпретируется
как оценка тренда; данные по зонам городов усреднены. Не является официальной оценкой.
""")
