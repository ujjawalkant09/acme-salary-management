"""Shows what a person sees on a page of the running app, so a new scenario uses only selectors
that really exist. Prints headings, buttons, links, form fields (by label), test ids, alerts,
dialogs and tables, and saves a screenshot.

Run from e2e/ (app.sh probe does this for the throwaway app):
  uv run python ../.claude/skills/as-user-oracles/scripts/probe.py /people/10 --as admin \
      --click "Change salary"
Uses the runner's settings: ORACLE_BASE_URL, DEMO_ADMIN_PASSWORD / DEMO_VIEWER_PASSWORD.
"""

import argparse
import os
import sys
from pathlib import Path

E2E = Path(__file__).resolve().parents[4] / "e2e"
sys.path.insert(0, str(E2E))

from oracle_kit import BACKEND_ENV, Ctx, open_browser, read_passwords  # noqa: E402

READ = r"""() => {
  const shown = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
  const text = el => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ')
  const all = selector => [...document.querySelectorAll(selector)].filter(shown)
  const name = el => text(el) || el.getAttribute('aria-label') || ''
  const tag = el => el.tagName.toLowerCase()
  const label = el =>
    el.getAttribute('aria-label') ||
    (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText) ||
    el.placeholder || el.name || '(no label)'
  const controls = '[role=menuitem], [role=tab], [role=option], [role=checkbox], [role=switch]'
  const columns = t => [...t.querySelectorAll('th')].map(text).join(' | ')
  return {
    url: location.pathname + location.search,
    headings: all('h1, h2, h3').map(h => `${tag(h)}  ${text(h)}`),
    buttons: all('button, [role=button]').map(name).filter(Boolean),
    controls: all(controls).map(c => `${c.getAttribute('role')}  ${text(c)}`),
    links: all('a[href]').map(a => `${name(a)}  -> ${a.getAttribute('href')}`),
    fields: all('input, select, textarea').map(
      f => `${label(f)}  (${tag(f)} ${f.type || ''}) = ${JSON.stringify(f.value)}`),
    test_ids: all('[data-testid]').map(e => `${e.dataset.testid}  ${text(e)}`),
    alerts: all('[role=alert], [data-sonner-toast]').map(text),
    dialogs: all('[role=dialog]').map(d => text(d).slice(0, 120)),
    tables: all('table').map(
      t => `${t.querySelectorAll('tbody tr').length} rows; columns: ${columns(t)}`),
  }
}"""


CLICKABLE = ("button", "menuitem", "tab", "option", "link")


def click(page, name: str) -> None:
    """Clicks the first button, menu item, tab, option or link with this name."""
    for role in CLICKABLE:
        target = page.get_by_role(role, name=name)
        if target.count():
            target.first.click()
            return
    raise SystemExit(f"nothing to click named {name!r}; see the buttons and controls above")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Show what a person sees on a page.")
    parser.add_argument("path", help="the page, for example /people or /people/10")
    parser.add_argument("--as", dest="role", choices=["admin", "viewer", "none"], default="admin")
    parser.add_argument("--click", action="append", default=[], help="a button to click first")
    args = parser.parse_args(argv)
    if not args.path.startswith("/"):
        parser.error("the path starts with /, for example /people")

    base_url = os.environ.get("ORACLE_BASE_URL", "http://localhost:8000").rstrip("/")
    passwords = read_passwords(os.environ, BACKEND_ENV)
    if args.role != "none" and args.role not in passwords:
        print(f"no {args.role} password: set DEMO_{args.role.upper()}_PASSWORD")
        return 3
    shot_dir = E2E / "screenshots"
    shot_dir.mkdir(exist_ok=True)

    with open_browser(headed=False) as browser:
        ctx = Ctx(base_url, passwords, False, shot_dir, browser)
        page = ctx.new_page()
        if args.role != "none":
            ctx.sign_in(page, args.role)
        page.goto(ctx.url(args.path))
        page.wait_for_load_state("networkidle")
        for name in args.click:
            click(page, name)
            # A click's requests start after it returns; a fixed pause is fine for a look, not
            # for a scenario (scenarios wait for what they expect to see).
            page.wait_for_timeout(800)
            page.wait_for_load_state("networkidle")
        seen = page.evaluate(READ)
        shot = ctx.shot(page, "probe")
        ctx.close_pages()

    print(f"url: {seen.pop('url')}")
    for section, items in seen.items():
        print(f"\n{section} ({len(items)})")
        for item in items:
            print(f"  {item}")
    print(f"\nscreenshot: {shot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
