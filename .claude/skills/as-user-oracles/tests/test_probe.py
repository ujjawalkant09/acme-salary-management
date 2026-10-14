"""probe.py without a browser: argument checks, a missing password, and what --click presses.
Run from e2e/: uv run pytest ../.claude/skills/as-user-oracles/tests"""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "probe", Path(__file__).resolve().parents[1] / "scripts" / "probe.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class FakeTarget:
    def __init__(self, page, role, name):
        self.page, self.role, self.name = page, role, name

    def count(self):
        return int((self.role, self.name) in self.page.present)

    @property
    def first(self):
        return self

    def click(self):
        self.page.clicked.append((self.role, self.name))


class FakePage:
    def __init__(self, *present):
        self.present = set(present)
        self.clicked = []

    def get_by_role(self, role, name):
        return FakeTarget(self, role, name)


def test_click_prefers_a_button_then_menu_items_tabs_and_links():
    page = FakePage(("menuitem", "Sign out"), ("link", "Sign out"), ("button", "Save"))
    probe.click(page, "Sign out")
    probe.click(page, "Save")
    assert page.clicked == [("menuitem", "Sign out"), ("button", "Save")]


def test_click_on_a_name_that_is_not_there_stops_with_a_clear_message():
    with pytest.raises(SystemExit, match="nothing to click named 'Nope'"):
        probe.click(FakePage(), "Nope")


def test_the_path_must_start_with_a_slash(capsys):
    with pytest.raises(SystemExit) as stop:
        probe.main(["people"])
    assert stop.value.code == 2
    assert "the path starts with /" in capsys.readouterr().err


def test_a_missing_password_stops_before_opening_a_browser(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(probe, "BACKEND_ENV", tmp_path / "missing.env")
    monkeypatch.delenv("DEMO_VIEWER_PASSWORD", raising=False)
    monkeypatch.setattr(probe, "open_browser", lambda headed: pytest.fail("browser opened"))
    assert probe.main(["/people", "--as", "viewer"]) == 3
    assert "no viewer password: set DEMO_VIEWER_PASSWORD" in capsys.readouterr().out
