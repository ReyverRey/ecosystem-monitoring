"""Smoke-тест дашборда: прогоняет все страницы через streamlit.testing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "app.py"


def nav_radio(at):
    """Навигационный radio в боковой панели (на страницах есть и другие)."""
    return next(r for r in at.radio if "Обзор" in list(r.options))


def pollutant_select(at):
    return next(s for s in at.selectbox if "CO" in [str(o) for o in s.options])


at = AppTest.from_file(str(APP), default_timeout=60)
at.run()
assert not at.exception, f"Обзор: {at.exception}"
print("Обзор: ok, заголовок:", at.title[0].value)

for page in ["Машина времени", "Динамика и сравнение", "Прогноз", "Тамагочи и квиз",
             "Экопаспорт и сценарии", "О данных"]:
    nav_radio(at).set_value(page).run()
    assert not at.exception, f"{page}: {at.exception}"
    print(f"{page}: ok")

nav_radio(at).set_value("Обзор").run()
pollutant_select(at).set_value("CO").run()
assert not at.exception, f"CO: {at.exception}"
print("переключение загрязнителя CO: ok")
print("SMOKE OK")
