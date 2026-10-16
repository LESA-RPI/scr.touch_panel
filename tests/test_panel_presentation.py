"""Weather meaning and pointer limits must remain correct as artwork changes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from panel_icons import weather_kind
from touch_slider import selected_value


def test_weather_symbols_preserve_day_night_and_precipitation_meaning():
    assert weather_kind(0) == 'sun'
    assert weather_kind(0, True) == 'moon'
    assert weather_kind(2) == 'cloud-sun'
    assert weather_kind(2, True) == 'cloud-moon'
    for code in (45,48):
        assert weather_kind(code, True) == 'cloud-fog'
    for code in (51,53,55,56,57,61,63,65,66,67,80,81,82):
        assert weather_kind(code) == 'cloud-rain'
    for code in (71,73,75,77,85,86):
        assert weather_kind(code) == 'cloud-snow'
    for code in (95,96,99):
        assert weather_kind(code) == 'cloud-lightning'
    assert weather_kind(-1) == 'circle-question-mark'


def test_touch_slider_clamps_drag_outside_track_and_honours_steps_in_both_directions():
    assert selected_value(-1,1600,10000,100) == 1600
    assert selected_value(2,1600,10000,100) == 10000
    assert selected_value(.51,1600,10000,100) == 5900
    assert selected_value(0,100,0,1) == 100
    assert selected_value(1,100,0,1) == 0
    assert selected_value(.755,100,0,1) == 25
