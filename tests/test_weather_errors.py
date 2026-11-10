"""Optional forecast failures must stay distinguishable from panel crashes."""

import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import weather


@pytest.mark.parametrize(
    "error",
    [
        URLError("network unavailable"),
        HTTPError("https://weather.invalid", 503, "Unavailable", {}, None),
        TimeoutError("forecast timed out"),
        ValueError("invalid forecast"),
        KeyError("current"),
    ],
)
def test_expected_forecast_failure_emits_json_without_traceback(
    monkeypatch, capsys, caplog, error
):
    def fail(*args):
        raise error

    monkeypatch.setattr(weather, "fetch", fail)
    weather.main(["0", "0", "UTC"])
    assert "room controls still work" in json.loads(capsys.readouterr().out)["error"]
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"
    assert caplog.records[0].exc_info is None


def test_unexpected_forecast_defect_keeps_diagnostic_traceback(monkeypatch, capsys, caplog):
    def fail(*args):
        raise RuntimeError("unexpected defect")

    monkeypatch.setattr(weather, "fetch", fail)
    weather.main(["0", "0", "UTC"])
    assert "error" in json.loads(capsys.readouterr().out)
    assert caplog.records[0].exc_info[0] is RuntimeError
