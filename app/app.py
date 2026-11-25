"""Дашборд «Мониторинг экосистемы»: качество воздуха по городам Беларуси.

Запуск:  streamlit run app/app.py
Страницы: Обзор, Машина времени, Динамика и сравнение, Прогноз, О данных.
Данные: data/processed/*.csv (offline, без внешних API — по ТЗ).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

st.set_page_config(page_title="Мониторинг экосистемы", page_icon="🌿", layout="wide")

sys.path.insert(0, str(ROOT / "src" / "features"))
sys.path.insert(0, str(ROOT / "app"))
import tamagotchi as tg  # noqa: E402
from passport import build as build_passport  # noqa: E402

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
                                      "Прогноз", "Тамагочи и квиз", "Экопаспорт и сценарии",
                                      "О данных"])
pol = st.sidebar.selectbox("Загрязняющее вещество", sorted(air["pollutant"].unique()),
                           format_func=lambda p: POLLUTANT_LABELS.get(p, p))

# ---- питомец в боковой панели (ТЗ 4.5) ----
st.sidebar.divider()
st.sidebar.markdown("### 🐾 Хранитель региона")
passport_df = build_passport()
pet_region = st.sidebar.selectbox("Регион питомца", passport_df["region"].tolist(),
                                  key="pet_region")
health = passport_df.loc[passport_df["region"] == pet_region, "index_equal_weights"].iloc[0]
health = None if pd.isna(health) else float(health)
pet_state = tg.get_state()
st.sidebar.markdown(f"**Уровень {pet_state['level']}** · опыт: {pet_state['xp']}")
st.sidebar.progress(int(pet_state["satiety"]),
                    text=f"Сытость: {pet_state['satiety']:.0f}/100")
if health is not None:
    st.sidebar.progress(int(health), text=f"Здоровье: {health:.0f}/100")
st.sidebar.caption(tg.mood(pet_state["satiety"], health))

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

elif page == "Тамагочи и квиз":
    import random

    st.header("🐾 Тамагочи — хранитель региона")
    st.markdown("Кормите питомца верными ответами: правильный ответ — порция еды. "
                "За один и тот же вопрос награда даётся не чаще раза в сутки.")
    questions = tg.load_questions()
    mode = st.radio("Режим", ["Квиз", "Угадай год"], horizontal=True)

    if mode == "Квиз":
        cats = ["все"] + sorted({q["category"] for q in questions})
        cat = st.selectbox("Категория", cats)
        pool = questions if cat == "все" else [q for q in questions if q["category"] == cat]
        qid = st.session_state.get("quiz_qid")
        if qid is None or not any(q["id"] == qid for q in pool):
            qid = random.choice(pool)["id"]
            st.session_state.quiz_qid = qid
        q = next(q for q in questions if q["id"] == qid)
        st.subheader(q["question"])
        st.caption(f"Источник: {q['source']}")
        choice = st.radio("Вариант ответа", q["options"], key=f"opt_{qid}")
        if st.session_state.get("quiz_feedback_qid") == qid:
            st.info(st.session_state.quiz_feedback)
            if st.button("Следующий вопрос"):
                st.session_state.pop("quiz_qid", None)
                st.session_state.pop("quiz_feedback_qid", None)
                st.rerun()
        elif st.button("Ответить"):
            correct = choice == q["options"][q["answer"]]
            rewarded_before = tg.can_reward(q["id"])
            tg.record_answer(q["id"], correct)
            if correct and rewarded_before:
                tg.feed(10)
                msg = "Верно! Питомец получил порцию еды (+10 опыта)."
            elif correct:
                msg = "Верно! Но за этот вопрос награда уже была в течение суток."
            else:
                msg = "Неверно. Попробуйте другой вопрос."
            st.session_state.quiz_feedback = msg
            st.session_state.quiz_feedback_qid = qid
            st.rerun()

    else:  # Угадай год
        if "guess" not in st.session_state or st.session_state.get("guess_done"):
            st.session_state.guess = tg.prepare_guess(rng=random.Random())
            st.session_state.guess_done = False
        g = st.session_state.guess
        if g is None:
            st.warning("Недостаточно данных для режима.")
        else:
            label = POLLUTANT_LABELS.get(g["pollutant"], g["pollutant"])
            st.subheader(f"Как изменится {label} в {g['city']}?")
            st.caption(f"Ряд с пропущенным годом; значение {g['prev_year']} года: "
                       f"{g['prev']:.1f}. Угадайте {g['hidden_year']} год.")
            st.line_chart(pd.Series(g["visible"]).sort_index(), height=280)
            c1, c2 = st.columns(2)
            direction = c1.radio("Направление", ["рост", "снижение"])
            magnitude = c2.radio("Размер изменения", ["до 5%", "5-15%", "более 15%"])
            if not st.session_state.guess_done:
                if st.button("Проверить"):
                    res = tg.evaluate_guess(direction, magnitude, g["actual_pct"])
                    mid = {"до 5%": 2.5, "5-15%": 10.0, "более 15%": 20.0}[magnitude]
                    est = mid if direction == "рост" else -mid
                    tg.record_guess(g["hidden_year"], direction, magnitude,
                                    g["actual_pct"], abs(est - g["actual_pct"]))
                    if res["points"]:
                        tg.feed(res["points"])
                    st.session_state.guess_done = True
                    st.session_state.guess_result = res
                    st.rerun()
            else:
                res = st.session_state.guess_result
                st.markdown(f"**Факт:** {g['actual']:.1f} ({g['actual_pct']:+.1f}% "
                            f"к {g['prev_year']} году) — {res['actual_dir']}, {res['actual_mag']}.")
                st.markdown(f"**Награда:** +{res['points']} еды.")
                if st.button("Ещё раз"):
                    st.session_state.guess_done = False
                    st.session_state.pop("guess", None)
                    st.rerun()
            stats = tg.guess_stats()
            if stats["n"]:
                st.markdown("---")
                st.markdown(f"**Ваша точность:** попыток {stats['n']}, средняя ошибка "
                            f"{stats['mean_abs_error']:.1f} п.п.; наивная модель "
                            f"(«без изменений») — {stats['naive_mean_abs_error']:.1f} п.п.")
                st.caption("Сравнение «человек против наивной модели» — научная часть "
                           "работы: результаты режима сопоставляются с точностью прогноза.")

elif page == "Экопаспорт и сценарии":
    import io
    import sys

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import plotly.graph_objects as go

    sys.path.insert(0, str(ROOT / "src" / "features"))
    from passport import build, score_with

    base = build()
    st.subheader("Экопаспорт региона")
    region = st.selectbox("Регион", base["region"].tolist())
    c1, c2, c3 = st.columns(3)
    w_air = c1.slider("Вес блока «воздух»", 0, 100, 33)
    w_water = c2.slider("Вес блока «вода»", 0, 100, 34)
    w_waste = c3.slider("Вес блока «отходы»", 0, 100, 33)
    weights = {"air": w_air, "water": w_water, "waste": w_waste}

    st.markdown("**Режим «что если»** — измените показатели, индекс пересчитается "
                "(сценарная оценка, не прогноз):")
    s1, s2, s3 = st.columns(3)
    m_air = s1.slider("Воздух: изменение, %", -50, 50, 0)
    m_water = s2.slider("Вода: изменение, %", -50, 50, 0)
    m_waste = s3.slider("Отходы: изменение, %", -50, 50, 0)
    multipliers = {"air": 1 + m_air / 100, "water": 1 + m_water / 100,
                   "waste": 1 + m_waste / 100}

    scen = score_with(base, weights, multipliers)
    baseline = score_with(base, weights)
    row_s = scen[scen["region"] == region].iloc[0]
    row_b = baseline[baseline["region"] == region].iloc[0]

    k1, k2 = st.columns(2)
    k1.metric("Индекс региона (сценарий)", f"{row_s['index']:.1f}")
    k2.metric("Индекс без изменений", f"{row_b['index']:.1f}")

    labels = ["Воздух", "Вода", "Отходы"]
    vals_s = [row_s["air_score"], row_s["water_score"], row_s["waste_score"]]
    vals_b = [row_b["air_score"], row_b["water_score"], row_b["waste_score"]]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=vals_b + [vals_b[0]], theta=labels + [labels[0]],
                                  name="без изменений", line=dict(dash="dash")))
    fig.add_trace(go.Scatterpolar(r=vals_s + [vals_s[0]], theta=labels + [labels[0]],
                                  name="сценарий", fill="toself"))
    fig.update_layout(height=480, polar=dict(radialaxis=dict(range=[0, 100])),
                      title=f"Профиль: {region} (100 — лучшее среди регионов)")
    st.plotly_chart(fig, width='stretch')

    st.subheader("Рейтинг регионов (сценарий)")
    st.dataframe(scen.sort_values("index", ascending=False).round(1), width='stretch')

    fig_m = plt.figure(figsize=(6, 6))
    ax = fig_m.add_subplot(111, polar=True)
    ang = [0, 2 * 3.14159265 / 3, 4 * 3.14159265 / 3, 0]
    ax.plot(ang, vals_b + [vals_b[0]], "--", label="без изменений")
    ax.plot(ang, vals_s + [vals_s[0]], "-", label="сценарий")
    ax.fill(ang, vals_s + [vals_s[0]], alpha=0.2)
    ax.set_xticks(ang[:-1])
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 100)
    ax.set_title(f"Экопаспорт: {region}")
    ax.legend(loc="lower right", fontsize=8)
    buf = io.BytesIO()
    fig_m.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig_m)
    st.download_button("Скачать карточку региона (PNG)", buf.getvalue(),
                       file_name=f"ecopassport_{region}.png", mime="image/png")
    st.caption("Методика: блоки «воздух» (концентрация/ПДК), «вода» (сброс вод), "
               "«отходы» (образование отходов), min-max нормировка по регионам, "
               "взвешенная сумма. Минская область: блок «воздух» отсутствует "
               "(нет городов в наборе) — индекс по двум блокам. Не является официальной оценкой.")

elif page == "О данных":
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
