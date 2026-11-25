"""Тамагочи — «хранитель региона» (ТЗ, п. 4.5).

Состояние хранится в SQLite (app/tamagotchi.db): опыт, время последнего кормления,
история ответов и догадок. Сытость вычисляется по времени последнего кормления
при открытии страницы (фоновых процессов нет). Питомец не умирает: при голоде грустит.

Награда едой:
- верный ответ в квизе (+10 опыта; один вопрос не даёт награду повторно в течение суток);
- режим «угадай год»: еда по точности (+15 за направление и размер изменения,
  +8 только за направление, 0 при промахе).

Здоровье зависит от индекса экопаспорта выбранного региона (0-100).
"""
import random
import sqlite3
import time
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "app" / "tamagotchi.db"
QUESTIONS_PATH = ROOT / "app" / "questions.yaml"
AIR_PATH = ROOT / "data" / "processed" / "air_belstat_tidy.csv"

USER = "default"
HUNGER_FULL_SECONDS = 8 * 3600  # сытость 100 -> 0 за 8 часов
REWARD_REPEAT_SECONDS = 24 * 3600


# ---------- состояние ----------
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS state (
        user TEXT PRIMARY KEY, xp INTEGER NOT NULL DEFAULT 0, last_feed_ts REAL NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS answers (
        user TEXT, question_id TEXT, ts REAL, correct INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS guesses (
        user TEXT, year INTEGER, direction TEXT, magnitude TEXT,
        actual_pct REAL, abs_error REAL, ts REAL)""")
    conn.commit()
    return conn


def get_state(user=USER):
    conn = _conn()
    row = conn.execute("SELECT xp, last_feed_ts FROM state WHERE user=?", (user,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO state (user, xp, last_feed_ts) VALUES (?, 0, ?)",
                     (user, time.time()))
        conn.commit()
        row = (0, time.time())
    conn.close()
    xp, last_feed_ts = row
    satiety = max(0.0, 100.0 * (1 - (time.time() - last_feed_ts) / HUNGER_FULL_SECONDS))
    return {"xp": xp, "level": xp // 100 + 1, "satiety": satiety, "last_feed_ts": last_feed_ts}


def feed(amount, user=USER):
    conn = _conn()
    state = get_state(user)
    conn.execute("UPDATE state SET xp = xp + ?, last_feed_ts = ? WHERE user=?",
                 (amount, time.time(), user))
    conn.commit()
    conn.close()
    return get_state(user)


def can_reward(question_id, user=USER):
    conn = _conn()
    row = conn.execute(
        "SELECT MAX(ts) FROM answers WHERE user=? AND question_id=? AND correct=1",
        (user, question_id)).fetchone()
    conn.close()
    return row[0] is None or (time.time() - row[0]) > REWARD_REPEAT_SECONDS


def record_answer(question_id, correct, user=USER):
    conn = _conn()
    conn.execute("INSERT INTO answers (user, question_id, ts, correct) VALUES (?, ?, ?, ?)",
                 (user, question_id, time.time(), int(correct)))
    conn.commit()
    conn.close()


def record_guess(year, direction, magnitude, actual_pct, abs_error, user=USER):
    conn = _conn()
    conn.execute("INSERT INTO guesses (user, year, direction, magnitude, actual_pct, abs_error, ts)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (user, year, direction, magnitude, actual_pct, abs_error, time.time()))
    conn.commit()
    conn.close()


def guess_stats(user=USER):
    conn = _conn()
    rows = conn.execute("SELECT abs_error, actual_pct FROM guesses WHERE user=?",
                        (user,)).fetchall()
    conn.close()
    errs = [r[0] for r in rows]
    naive = [abs(r[1]) for r in rows]  # наивная модель: «без изменений» (0%)
    return {"n": len(errs),
            "mean_abs_error": sum(errs) / len(errs) if errs else None,
            "naive_mean_abs_error": sum(naive) / len(naive) if naive else None}


# ---------- настроение ----------
def mood(satiety, health):
    if satiety < 25:
        return "🥺 Грустит — хочет есть"
    if health is None:
        return "🙂 Нормально"
    if health >= 66:
        return "😊 Бодр"
    if health >= 33:
        return "😐 Нормально"
    return "😷 Кашляет — воздух в регионе плохой"


# ---------- вопросы ----------
def load_questions():
    manual = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    for q in manual:
        q["source"] = "ручной банк"
    return manual + generate_dataset_questions()


def generate_dataset_questions():
    """Вопросы, генерируемые из датасета (детерминированно)."""
    df = pd.read_csv(AIR_PATH)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    conc = (df[df["indicator"].str.startswith("Среднегодовая концентрация")]
            .groupby(["city", "pollutant", "year"], as_index=False)["value"].mean()
            .dropna(subset=["value"]))
    rng = random.Random(2026)
    questions = []
    gid = 1
    for pol in ["CO", "NO2", "PM10"]:
        sub = conc[conc["pollutant"] == pol]
        if sub.empty:
            continue
        years = sorted(sub["year"].unique())
        y0, y1 = years[0], years[-1]
        # A: год с максимумом средней концентрации
        nat = sub.groupby("year")["value"].mean()
        peak = int(nat.idxmax())
        distract_years = rng.sample([y for y in years if y != peak], k=3)
        options = [str(peak)] + [str(y) for y in distract_years]
        rng.shuffle(options)
        questions.append({
            "id": f"g{gid:02d}", "category": "из данных", "source": "генерация из датасета",
            "question": f"В каком году средняя концентрация {pol} по городам была самой "
                        f"высокой в период {y0}–{y1}?",
            "options": options, "answer": options.index(str(peak))})
        gid += 1
        # B: город с максимальным ростом
        piv = sub[sub["year"].isin([y0, y1])].pivot(index="city", columns="year", values="value")
        piv = piv.dropna()
        if len(piv) >= 4 and y1 in piv.columns and y0 in piv.columns:
            delta = (piv[y1] - piv[y0]).sort_values(ascending=False)
            top_city = delta.index[0]
            distract = rng.sample([c for c in delta.index if c != top_city], k=3)
            options = [top_city] + distract
            rng.shuffle(options)
            questions.append({
                "id": f"g{gid:02d}", "category": "из данных", "source": "генерация из датасета",
                "question": f"В каком городе концентрация {pol} выросла сильнее всего "
                            f"с {y0} по {y1} год?",
                "options": options, "answer": options.index(top_city)})
            gid += 1
    return questions


# ---------- «угадай год» ----------
def prepare_guess(pol="CO", city=None, rng=None):
    """Прячет один год: возвращает данные ряда с дырой и факт для сверки."""
    rng = rng or random.Random()
    df = pd.read_csv(AIR_PATH)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    conc = (df[df["indicator"].str.startswith("Среднегодовая концентрация")]
            .groupby(["city", "pollutant", "year"], as_index=False)["value"].mean()
            .dropna(subset=["value"]))
    sub = conc[conc["pollutant"] == pol]
    if city:
        sub = sub[sub["city"] == city]
    else:
        cities = sorted(sub["city"].unique())
        city = rng.choice(cities)
        sub = sub[sub["city"] == city]
    s = sub.set_index("year")["value"].sort_index()
    candidates = [y for y in s.index if y - 1 in s.index]
    if not candidates:
        return None
    hidden = rng.choice(candidates)
    prev = float(s.loc[hidden - 1])
    actual = float(s.loc[hidden])
    actual_pct = (actual - prev) / prev * 100
    return {"city": city, "pollutant": pol, "hidden_year": hidden,
            "prev_year": hidden - 1, "prev": prev, "actual": actual,
            "actual_pct": actual_pct,
            "visible": {int(y): float(v) for y, v in s.items() if y != hidden}}


def evaluate_guess(direction, magnitude, actual_pct):
    """direction: 'рост' | 'снижение'; magnitude: 'до 5%' | '5-15%' | 'более 15%'."""
    if actual_pct == 0:
        actual_dir = "без изменений"
    else:
        actual_dir = "рост" if actual_pct > 0 else "снижение"
    a = abs(actual_pct)
    actual_mag = "до 5%" if a < 5 else ("5-15%" if a <= 15 else "более 15%")
    if direction == actual_dir and magnitude == actual_mag:
        points = 15
    elif direction == actual_dir:
        points = 8
    else:
        points = 0
    return {"points": points, "actual_dir": actual_dir, "actual_mag": actual_mag}
