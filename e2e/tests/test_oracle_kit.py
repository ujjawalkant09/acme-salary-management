"""Tests for the harness itself: no browser and no real app (a fake browser and a local
health server stand in)."""

import json
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import oracle_kit
from oracle_kit import Checks, Ctx, Oracle, Outcome, check_app, read_passwords, run_one

HEAD = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


# ---- fakes ----------------------------------------------------------------------
class FakeContext:
    def __init__(self):
        self.closed = False

    def set_default_timeout(self, _ms):
        pass

    def new_page(self):
        return "page"

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.contexts = []

    def new_context(self, **_options):
        self.contexts.append(FakeContext())
        return self.contexts[-1]


def make_ctx(tmp_path, allow_writes=False):
    return Ctx("http://app", {"admin": "a", "viewer": "v"}, allow_writes, tmp_path, FakeBrowser())


@contextmanager
def health_server(body: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def oracle_with(*ids):
    oracle = Oracle("demo")
    for sid in ids:
        oracle.scenario(sid, f"scenario {sid}")(lambda page, ctx: Checks())
    return oracle


# ---- Checks and Oracle ------------------------------------------------------------
def test_checks_record_every_result_and_keep_going_after_a_fail():
    ck = Checks()
    assert ck.that(True, "first") is True
    assert ck.that(False, "second") is False
    ck.that(True, "third")
    assert ck.lines == ["PASS  first", "FAIL  second", "PASS  third"]
    assert ck.failures == ["second"]


def test_a_scenario_id_used_twice_is_refused():
    oracle = oracle_with("S1")
    with pytest.raises(ValueError, match="S1 is used twice"):
        oracle.scenario("S1", "again")(lambda page, ctx: Checks())


def test_scenarios_run_in_number_order_not_text_order():
    assert oracle_with("S10", "S2", "S1").ordered() == ["S1", "S2", "S10"]


def test_select_takes_ids_and_ranges_without_repeats():
    oracle = oracle_with("S1", "S2", "S3", "S4", "S10")
    assert oracle.select([]) == (["S1", "S2", "S3", "S4", "S10"], [])
    assert oracle.select(["S3", "S1-S3"]) == (["S3", "S1", "S2"], [])
    assert oracle.select(["S2-S2"]) == (["S2"], [])


def test_select_reports_ids_and_ranges_that_match_nothing():
    oracle = oracle_with("S1", "S2")
    assert oracle.select(["S1", "S9", "S5-S7", "golden"]) == (["S1"], ["S9", "S5-S7", "golden"])


# ---- run_one ----------------------------------------------------------------------
def test_run_one_turns_checks_into_green_or_red_and_closes_the_page(tmp_path):
    ctx = make_ctx(tmp_path)

    def passing(page, ctx):
        ck = Checks()
        ck.that(page == "page", "got a page")
        ck.note("shot.png")
        return ck

    def failing(page, ctx):
        ck = Checks()
        ck.that(False, "broken")
        return ck

    green = run_one(passing, ctx)
    assert (green.status, green.detail, green.evidence) == (
        "GREEN",
        "PASS  got a page",
        ["shot.png"],
    )
    assert run_one(failing, ctx).status == "RED"
    assert all(context.closed for context in ctx.browser.contexts)


def test_run_one_makes_a_crash_red_and_passes_a_skip_through(tmp_path):
    ctx = make_ctx(tmp_path)

    def crashing(page, ctx):
        ctx.new_page()  # a second page must be closed too
        raise RuntimeError("selector not found")

    red = run_one(crashing, ctx)
    assert red.status == "RED"
    assert "EXCEPTION: selector not found" in red.detail
    assert len(ctx.browser.contexts) == 2 and all(c.closed for c in ctx.browser.contexts)
    assert run_one(lambda page, ctx: Outcome.skip("no data"), ctx).detail == "SKIP: no data"


def test_scenarios_that_change_data_skip_unless_writes_are_allowed(tmp_path):
    refused = make_ctx(tmp_path).writes_refused()
    assert refused.status == "SKIP" and "ORACLE_ALLOW_WRITES=1" in refused.detail
    assert make_ctx(tmp_path, allow_writes=True).writes_refused() is None


# ---- gates --------------------------------------------------------------------------
def test_app_gate_fails_when_the_app_does_not_answer():
    up, message = check_app("http://127.0.0.1:9")
    assert not up and message.startswith("DOWN")


def test_app_gate_passes_a_build_from_this_checkout_or_from_source():
    with health_server({"status": "ok", "commit": HEAD[:12]}) as url:
        assert check_app(url) == (
            True,
            f"OK    {url} runs commit {HEAD[:12]}, the same as this checkout",
        )
    with health_server({"status": "ok", "commit": None}) as url:
        up, message = check_app(url)
        assert up and "running from source" in message


def test_app_gate_stops_a_build_from_another_commit():
    with health_server({"status": "ok", "commit": "0000000deadb"}) as url:
        up, message = check_app(url)
    assert not up and message.startswith("FOREIGN") and "0000000deadb" in message


def test_passwords_come_from_the_environment_first_then_the_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# DEMO_ADMIN_PASSWORD=commented-out\n"
        "DEMO_ADMIN_PASSWORD='from-file'\n"
        'DEMO_VIEWER_PASSWORD="viewer-from-file"\n'
    )
    assert read_passwords({}, env_file) == {"admin": "from-file", "viewer": "viewer-from-file"}
    from_env = read_passwords({"DEMO_ADMIN_PASSWORD": "from-env"}, env_file)
    assert from_env == {"admin": "from-env", "viewer": "viewer-from-file"}
    assert read_passwords({}, tmp_path / "missing.env") == {}


# ---- main: exit codes ------------------------------------------------------------
@pytest.fixture
def runner(tmp_path, monkeypatch):
    """main() wired to one fake 'demo' feature, a passing app gate and a fake browser."""
    oracle = Oracle("demo")
    monkeypatch.setattr(oracle_kit, "feature_names", lambda: ["demo"])
    monkeypatch.setattr(oracle_kit, "load", lambda name: oracle)
    monkeypatch.setattr(oracle_kit, "check_app", lambda url: (True, "OK"))
    monkeypatch.setattr(oracle_kit, "BACKEND_ENV", tmp_path / "no.env")

    @contextmanager
    def fake_browser(headed):
        yield FakeBrowser()

    monkeypatch.setattr(oracle_kit, "open_browser", fake_browser)
    env = {
        "DEMO_ADMIN_PASSWORD": "a",
        "DEMO_VIEWER_PASSWORD": "v",
        "ORACLE_SHOT_DIR": str(tmp_path),
    }
    return oracle, env


def test_main_exits_0_when_nothing_is_red_and_1_when_something_is(runner, capsys):
    oracle, env = runner
    oracle.scenario("S1", "works")(lambda page, ctx: Checks())
    oracle.scenario("S2", "no data")(lambda page, ctx: Outcome.skip("empty"))
    assert oracle_kit.main(["demo"], env) == 0
    assert "1/2 green, 1 skipped" in capsys.readouterr().out

    oracle.scenario("S3", "broken")(lambda page, ctx: Outcome("RED", "FAIL  x"))
    assert oracle_kit.main(["demo"], env) == 1
    assert "RED   demo S3 broken" in capsys.readouterr().out


def test_main_exits_2_for_an_unknown_scenario_before_opening_anything(runner, monkeypatch):
    oracle, env = runner
    oracle.scenario("S1", "works")(lambda page, ctx: Checks())
    monkeypatch.setattr(oracle_kit, "check_app", lambda url: pytest.fail("gate ran"))
    assert oracle_kit.main(["demo", "S7"], env) == 2


def test_main_exits_3_when_a_password_is_missing(runner):
    oracle, env = runner
    oracle.scenario("S1", "works")(lambda page, ctx: Checks())
    del env["DEMO_VIEWER_PASSWORD"]
    assert oracle_kit.main(["demo"], env) == 3


def test_main_exits_4_when_the_app_gate_fails(runner, monkeypatch):
    oracle, env = runner
    oracle.scenario("S1", "works")(lambda page, ctx: Checks())
    monkeypatch.setattr(oracle_kit, "check_app", lambda url: (False, "DOWN"))
    assert oracle_kit.main(["demo"], env) == 4


def test_all_cannot_be_combined_with_scenario_ids(runner):
    _, env = runner
    with pytest.raises(SystemExit):
        oracle_kit.main(["all", "S1"], env)


def test_every_feature_file_loads_and_has_scenarios():
    for name in oracle_kit.feature_names():
        oracle = oracle_kit.load(name)
        assert oracle.feature == name and oracle.specs, name
