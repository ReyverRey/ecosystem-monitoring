"""Юнит-тесты: тамагочи, экопаспорт, разбор значений (ТЗ, п. 5)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src" / "features"))
sys.path.insert(0, str(ROOT / "src" / "clean"))

import tamagotchi as tg
from parse_belstat_a2 import parse_cell
from passport import build, score_with

U = "test_user"


def test_parse_cell():
    assert parse_cell("150") == [(150.0, "", "")]
    assert parse_cell("…") == [(None, "", "")]
    v, z, n = parse_cell("13 (жилой район)")[0]
    assert v == 13.0 and z == "жилой район"
    v, z, n = parse_cell("1 (жилой район) 71 (пром. район)")[0]
    assert v == 1.0 and z == "жилой район"
    assert len(parse_cell("1 (жилой район) 71 (пром. район)")) == 2
    v, _, n = parse_cell("16-21")[0]
    assert v == 18.5 and "диапазон" in n
    assert parse_cell("мкг/м3")[0][0] is None


def test_tamagotchi_feed_and_reward():
    import time
    state = tg.feed(10, user=U)
    assert state["xp"] >= 10
    assert 0 <= state["satiety"] <= 100
    qid = f"unit-test-question-{time.time()}"  # уникальный ID: повторный запуск теста не мешает
    assert tg.can_reward(qid, user=U) is True
    tg.record_answer(qid, True, user=U)
    assert tg.can_reward(qid, user=U) is False  # повторно в течение суток нельзя


def test_guess_evaluation():
    res = tg.evaluate_guess("рост", "5-15%", 7.0)
    assert res["points"] == 15
    res = tg.evaluate_guess("рост", "более 15%", 7.0)
    assert res["points"] == 8
    res = tg.evaluate_guess("снижение", "до 5%", 7.0)
    assert res["points"] == 0


def test_passport_index():
    df = build()
    assert len(df) == 7
    scen = score_with(df, {"air": 1, "water": 1, "waste": 1}, {"waste": 1.5})
    base = score_with(df, {"air": 1, "water": 1, "waste": 1})
    # рост отходов не должен улучшать индекс
    merged = scen.merge(base, on="region", suffixes=("_s", "_b"))
    assert (merged["index_s"] <= merged["index_b"] + 1e-9).all()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"{name}: ok")
    print("UNITS OK")
