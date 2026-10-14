"""As-user oracles: check ACME Pay in a real browser, the way a person uses it.

Each file in features/ is one oracle: numbered scenarios (S1, S2, …) that click through
the running app and read what a person sees. Each scenario ends:
  GREEN  every check passed
  RED    a check failed or the scenario crashed
  SKIP   the environment lacks what the scenario needs (never counted as GREEN)

Run:  uv run python oracle_kit.py <feature|all> [S1 S2 | S1-S3]
Exit: 0 no RED · 1 a RED · 2 unknown scenario id · 3 missing password · 4 wrong or no app
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

HERE = Path(__file__).resolve().parent
FEATURES = HERE / "features"
BACKEND_ENV = HERE.parent / "backend" / ".env"

# The two demo logins made by the seed script, and where each password comes from.
USERS = {
    "admin": ("priya.sharma@acme.example", "DEMO_ADMIN_PASSWORD"),
    "viewer": ("arjun.mehta@acme.example", "DEMO_VIEWER_PASSWORD"),
}


# ---- the result of one scenario ----------------------------------------------
class Checks:
    """Records every check; a FAIL does not stop the scenario."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures: list[str] = []
        self.evidence: list[str] = []

    def that(self, condition: bool, message: str) -> bool:
        self.lines.append(("PASS  " if condition else "FAIL  ") + message)
        if not condition:
            self.failures.append(message)
        return condition

    def note(self, path: str) -> None:
        self.evidence.append(path)


@dataclass
class Outcome:
    status: str  # GREEN, RED or SKIP
    detail: str = ""
    evidence: list[str] = field(default_factory=list)

    @classmethod
    def skip(cls, reason: str) -> "Outcome":
        return cls("SKIP", "SKIP: " + reason)


# ---- an oracle: one feature's numbered scenarios ------------------------------
Scenario = Callable[[Page, "Ctx"], "Checks | Outcome"]


class Oracle:
    def __init__(self, feature: str) -> None:
        self.feature = feature
        self.specs: dict[str, tuple[str, Scenario]] = {}

    def scenario(self, sid: str, title: str) -> Callable[[Scenario], Scenario]:
        def register(fn: Scenario) -> Scenario:
            if sid in self.specs:  # a second S3 would silently replace the first
                raise ValueError(f"{self.feature}: scenario id {sid} is used twice")
            self.specs[sid] = (title, fn)
            return fn

        return register

    def ordered(self) -> list[str]:
        return sorted(self.specs, key=_number)

    def select(self, ids: list[str]) -> tuple[list[str], list[str]]:
        """The scenario ids to run (all when `ids` is empty) and the ids that matched nothing."""
        if not ids:
            return self.ordered(), []
        chosen, unknown = [], []
        for token in ids:
            if "-" in token:
                low, high = (_number(part) for part in token.split("-", 1))
                matched = [s for s in self.ordered() if low <= _number(s) <= high]
            else:
                matched = [token] if token in self.specs else []
            chosen += matched
            if not matched:
                unknown.append(token)
        return list(dict.fromkeys(chosen)), unknown


def _number(sid: str) -> int:
    digits = sid.strip().upper().removeprefix("S")
    return int(digits) if digits.isdigit() else -1


# ---- what every scenario gets: the app, the logins and the browser ------------
@dataclass
class Ctx:
    base_url: str
    passwords: dict[str, str]
    allow_writes: bool
    shot_dir: Path
    browser: Browser | None = None
    _cookies: dict[str, list] = field(default_factory=dict)
    _contexts: list = field(default_factory=list)

    def url(self, path: str) -> str:
        return self.base_url + path

    def new_page(self) -> Page:
        """A page in its own browser context, so it shares no cookies with other pages."""
        # The server's dates are UTC; a browser past local midnight would date "today" tomorrow.
        context = self.browser.new_context(
            viewport={"width": 1440, "height": 900}, timezone_id="UTC"
        )
        context.set_default_timeout(15_000)
        self._contexts.append(context)
        return context.new_page()

    def close_pages(self) -> None:
        for context in self._contexts:
            context.close()
        self._contexts.clear()

    def sign_in(self, page: Page, role: str) -> None:
        """Signs in through the form once per role and run; later scenarios reuse the cookie
        (the app allows 5 sign-ins a minute)."""
        if role in self._cookies:
            page.context.add_cookies(self._cookies[role])
            page.goto(self.url("/"))
        else:
            email, _ = USERS[role]
            submit_login(page, self, email, self.passwords[role])
        nav = page.get_by_role("navigation", name="Main")
        page.locator('nav[aria-label="Main"], form [role="alert"]').first.wait_for()
        if not nav.is_visible():
            problem = page.locator('form [role="alert"]').first.inner_text()
            raise RuntimeError(f"sign-in as {role} failed: {problem}")
        self._cookies[role] = page.context.cookies()

    def shot(self, page: Page, name: str) -> str:
        path = self.shot_dir / f"{name}.png"
        page.screenshot(path=path)
        return str(path)

    def writes_refused(self) -> Outcome | None:
        """A SKIP for scenarios that change data, unless the run allows it."""
        if self.allow_writes:
            return None
        return Outcome.skip("changes data; set ORACLE_ALLOW_WRITES=1 on a throwaway database")


def submit_login(page: Page, ctx: Ctx, email: str, password: str) -> None:
    page.goto(ctx.url("/"))
    page.get_by_label("Work email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").click()


def open_employee(page: Page, ctx: Ctx, code: str) -> bool:
    """Finds an employee by code on People and opens their page, as a person does.
    False when the search finds no one (the database lacks that employee)."""
    page.goto(ctx.url(f"/people?q={code}"))
    rows = page.locator("main tbody tr")
    page.locator("main tbody tr, main h2:text('No one matches')").first.wait_for()
    if rows.count() != 1:
        return False
    rows.first.click()
    salary_history(page).first.wait_for()
    return True


def salary_history(page: Page):
    """The rows of the Salary history table on an employee page. Not found by role: an open
    dialog hides the page behind it from role queries."""
    section = page.locator("section", has=page.locator("h2", has_text="Salary history"))
    return section.locator("tbody tr")


def eventually(read: Callable[[], object], expected: object, timeout_s: float = 10) -> object:
    """Polls `read` until it returns `expected` or time runs out; returns the last value."""
    deadline = time.monotonic() + timeout_s
    value = read()
    while value != expected and time.monotonic() < deadline:
        time.sleep(0.2)
        value = read()
    return value


# ---- gates: stop before a RED that the app is not to blame for ----------------
def check_app(base_url: str) -> tuple[bool, str]:
    """Is the app up, and is it built from this checkout? Running from source has no commit."""
    try:
        with urllib.request.urlopen(base_url + "/api/v1/health", timeout=10) as response:
            commit = json.load(response).get("commit")
    except (OSError, ValueError) as exc:
        return False, f"DOWN  {base_url}/api/v1/health does not answer: {exc}"
    if not commit:
        return True, f"OK    {base_url} is up (running from source, no build commit to compare)"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True)
    if head.returncode != 0:
        return True, f"OK    {base_url} runs commit {commit} (no git here to compare)"
    if not head.stdout.strip().startswith(commit):
        return (
            False,
            f"FOREIGN  {base_url} runs commit {commit}, this checkout is {head.stdout[:12]}",
        )
    return True, f"OK    {base_url} runs commit {commit}, the same as this checkout"


def read_passwords(env: dict[str, str], env_file: Path) -> dict[str, str]:
    """Each demo password from the environment, else from backend/.env. Quotes are stripped:
    a quoted value copied as is fails every sign-in."""
    from_file = {}
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.lstrip().startswith("#"):
                from_file[key.strip()] = value.strip().strip("'\"")
    passwords = {}
    for role, (_, variable) in USERS.items():
        value = env.get(variable) or from_file.get(variable)
        if value:
            passwords[role] = value
    return passwords


# ---- the runner ---------------------------------------------------------------
def feature_names() -> list[str]:
    return sorted(p.stem for p in FEATURES.glob("*.py"))


def load(feature: str) -> Oracle:
    spec = importlib.util.spec_from_file_location(f"oracle_{feature}", FEATURES / f"{feature}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.ORACLE


def run_one(fn: Scenario, ctx: Ctx) -> Outcome:
    page = ctx.new_page()
    try:
        result = fn(page, ctx)
        if isinstance(result, Checks):
            status = "RED" if result.failures else "GREEN"
            return Outcome(status, "\n      ".join(result.lines), result.evidence)
        return result
    except Exception as exc:  # a crash is a RED, with the trace as the detail
        return Outcome("RED", f"EXCEPTION: {exc}\n{traceback.format_exc()}")
    finally:
        ctx.close_pages()


@contextmanager
def open_browser(headed: bool):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        try:
            yield browser
        finally:
            browser.close()


def main(argv: list[str], env: dict[str, str] = os.environ) -> int:
    parser = argparse.ArgumentParser(description="Run as-user oracles against a running app.")
    parser.add_argument("feature", choices=[*feature_names(), "all"])
    parser.add_argument("ids", nargs="*", help="S1 S2, or a range S1-S3 (one feature only)")
    args = parser.parse_args(argv)
    if args.feature == "all" and args.ids:
        parser.error("scenario ids need one feature, not 'all'")

    oracles = [
        load(name) for name in (feature_names() if args.feature == "all" else [args.feature])
    ]
    plan = []
    for oracle in oracles:
        ids, unknown = oracle.select(args.ids)
        if unknown:
            print(f"no scenario {', '.join(unknown)} in {oracle.feature}: has {oracle.ordered()}")
            return 2
        plan += [(oracle, sid) for sid in ids]

    print("--- app gate ---")
    base_url = env.get("ORACLE_BASE_URL", "http://localhost:8000").rstrip("/")
    up, message = check_app(base_url)
    print(message)
    if not up:
        return 4

    print("--- login gate ---")
    passwords = read_passwords(env, BACKEND_ENV)
    missing = [USERS[role][1] for role in USERS if role not in passwords]
    if missing:
        print(f"missing {', '.join(missing)}: set it, or put it in backend/.env")
        return 3
    print("OK    both demo passwords are set")

    shot_dir = Path(env.get("ORACLE_SHOT_DIR", HERE / "screenshots"))
    shot_dir.mkdir(parents=True, exist_ok=True)
    ctx = Ctx(base_url, passwords, env.get("ORACLE_ALLOW_WRITES") == "1", shot_dir)

    results = []
    with open_browser(env.get("ORACLE_HEADED") == "1") as browser:
        ctx.browser = browser
        for oracle, sid in plan:
            title, fn = oracle.specs[sid]
            started = time.monotonic()
            outcome = run_one(fn, ctx)
            seconds = time.monotonic() - started
            print(f"\n[{outcome.status}] {oracle.feature} {sid} {title}  ({seconds:.1f}s)")
            if outcome.detail:
                print("      " + outcome.detail)
            for path in outcome.evidence:
                print("      evidence:", path)
            results.append((f"{oracle.feature} {sid}", title, outcome.status))

    print("\n=== summary ===")
    for name, title, status in results:
        print(f"  {status:<5} {name} {title}")
    reds = sum(status == "RED" for *_, status in results)
    skips = sum(status == "SKIP" for *_, status in results)
    print(f"\n{len(results) - reds - skips}/{len(results)} green, {skips} skipped")
    return 1 if reds else 0


if __name__ == "__main__":
    # Run the imported module, not __main__, so the feature files share its Checks and Outcome.
    import oracle_kit

    raise SystemExit(oracle_kit.main(sys.argv[1:]))
