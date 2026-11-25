"""Smoke-тест дашборда: прогоняет все страницы через streamlit.testing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "app.py"

at = AppTest.from_file(str(APP), default_timeout=60)
at.run()
assert not at.exception, f"Обзор: {at.exception}"
print("Обзор: ok, заголовок:", at.title[0].value)

for page in ["Машина времени", "Динамика и сравнение", "Прогноз", "Экопаспорт и сценарии", "О данных"]:
    at.radio[0].set_value(page).run()
    assert not at.exception, f"{page}: {at.exception}"
    print(f"{page}: ok")

at.radio[0].set_value("Обзор").run()
at.selectbox[0].set_value("CO").run()
assert not at.exception, f"CO: {at.exception}"
print("переключение загрязнителя CO: ok")
print("SMOKE OK")
