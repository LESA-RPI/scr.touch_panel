"""Original return checks require the exact event-loop response, never a title."""

import json
import sys
from types import SimpleNamespace

import pytest

from test_scr_touch_panel import panel
import original_idle


class Interpreter:
    def __init__(self, replies=None, names=None):
        self.calls = []
        self.replies = replies if replies is not None else {
            "beta": (100, 1, "LESA Smart Conference Room · Beta"),
            "main": (200, 1, "main"),
        }
        self.names = names if names is not None else ["observer"] + list(self.replies)

    def call(self, *args):
        self.calls.append(args)
        if args == ("tk", "appname"):
            return "observer"
        if args == ("winfo", "interps"):
            return tuple(self.names)
        assert args[:2] == ("send", "--")
        assert len(args) == 4 and args[3] == original_idle.QUERY
        reply = self.replies[args[2]]
        if isinstance(reply, Exception):
            raise reply
        return reply

    @staticmethod
    def splitlist(value):
        assert isinstance(value, tuple)
        return value


def test_probe_matches_pid_and_never_sends_to_itself_or_invokes_a_widget():
    interpreter = Interpreter()
    result = original_idle.probe(interpreter, 200)
    assert result == {"version": 1, "idle": True, "pid": 200,
                      "app_name": "main", "title": "main"}
    assert interpreter.calls == [("tk", "appname"), ("winfo", "interps"),
                                 ("send", "--", "beta", original_idle.QUERY),
                                 ("send", "--", "main", original_idle.QUERY)]
    assert original_idle.QUERY == "list [pid] [winfo exists .] [wm title .]"


def test_probe_does_not_guess_original_from_a_matching_title():
    interpreter = Interpreter({"main": (201, 1, "main")})
    with pytest.raises(ValueError, match="exact original"):
        original_idle.probe(interpreter, 200)


@pytest.mark.parametrize("replies", [
    {},
    {"main": (200, 0, "main")},
    {"main": (200, 1, "main"), "main #2": (200, 1, "main")},
])
def test_missing_closed_or_ambiguous_original_is_not_idle(replies):
    with pytest.raises(ValueError, match="exact original"):
        original_idle.probe(Interpreter(replies), 200)


@pytest.mark.parametrize("reply", [(200,), ("bad", 1, "main"),
                                    (200, "bad", "main"),
                                    RuntimeError("X server send unavailable")])
def test_unreadable_target_never_falls_back_to_another_identity(reply):
    with pytest.raises((ValueError, RuntimeError)):
        original_idle.probe(Interpreter({"main": reply}), 200)


def test_application_names_are_passed_as_data():
    name = "main; arbitrary-script [or-command]"
    interpreter = Interpreter({name: (200, 1, "main")})
    assert original_idle.probe(interpreter, 200)["app_name"] == name
    assert interpreter.calls[-1] == ("send", "--", name, original_idle.QUERY)


@pytest.mark.parametrize("pid", [0, -1, True, "200"])
def test_invalid_pid_is_rejected_before_any_tk_query(pid):
    interpreter = Interpreter()
    with pytest.raises(ValueError, match="positive"):
        original_idle.probe(interpreter, pid)
    assert interpreter.calls == []


@pytest.mark.parametrize("available", [False, True])
def test_cli_emits_one_json_result_and_destroys_only_its_own_window(
    monkeypatch, capsys, available,
):
    events = []
    root = SimpleNamespace(tk=Interpreter() if available else Interpreter({}),
                           withdraw=lambda: events.append("withdraw"),
                           destroy=lambda: events.append("destroy"))
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(Tk=lambda: root))
    assert original_idle.main(["--pid", "200"]) == (0 if available else 1)
    result = json.loads(capsys.readouterr().out)
    assert result["idle"] is available
    assert events == ["withdraw", "destroy"]
