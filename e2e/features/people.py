"""Oracle: the People list (search, empty state, opening a person). Click paths: people.md."""

import re

from oracle_kit import Checks, Oracle, Outcome, eventually

ORACLE = Oracle("people")

PAGE_SIZE = 20


def open_people(page, ctx):
    ctx.sign_in(page, "admin")
    page.goto(ctx.url("/people"))
    page.locator("main tbody tr").first.wait_for()


def shown_count(page) -> str:
    """The "967 people" line above the table."""
    return page.locator("main [aria-live='polite']").inner_text().strip()


def search(page, text):
    page.get_by_role("searchbox", name="Search people").fill(text)


@ORACLE.scenario("S1", "the list opens with a full first page and a head count")
def list_opens(page, ctx):
    ck = Checks()
    open_people(page, ctx)
    rows = page.locator("main tbody tr").count()
    count = shown_count(page)
    total = int(re.sub(r"\D", "", count) or 0)
    ck.that(total > 0, f"head count reads {count!r}")
    ck.that(rows == min(PAGE_SIZE, total), f"{rows} rows on page 1 of {total} people")
    pager = page.get_by_text(re.compile(r"^Page 1 of")).inner_text()
    ck.that(pager.startswith("Page 1 of"), f"pager reads {pager!r}")
    ck.note(ctx.shot(page, "people-S1"))
    return ck


@ORACLE.scenario("S2", "searching an employee code finds exactly that person")
def search_by_code(page, ctx):
    open_people(page, ctx)
    search(page, "ACM-000010")
    count = eventually(lambda: shown_count(page), "1 person")
    if count == "0 people":
        return Outcome.skip("employee ACM-000010 is not in this database")
    ck = Checks()
    ck.that(count == "1 person", f"head count reads {count!r}")
    row = page.locator("main tbody tr").first.inner_text()
    ck.that("ACM-000010" in row, f"the row is {row.splitlines()[:3]}")
    ck.that("q=ACM-000010" in page.url, f"the search is in the link: {page.url}")
    ck.note(ctx.shot(page, "people-S2"))
    return ck


@ORACLE.scenario("S3", "a search that matches no one says so, and Clear brings everyone back")
def no_match(page, ctx):
    ck = Checks()
    open_people(page, ctx)
    before = shown_count(page)
    search(page, "zzqx-no-such-person")
    empty = page.get_by_role("heading", name="No one matches")
    empty.wait_for()
    ck.that(shown_count(page) == "0 people", f"head count reads {shown_count(page)!r}")
    ck.that(page.locator("main tbody tr").count() == 0, "no rows are shown")
    ck.note(ctx.shot(page, "people-S3-empty"))
    page.get_by_role("button", name="Clear all filters").click()
    after = eventually(lambda: shown_count(page), before)
    ck.that(after == before, f"after Clear the count is {after!r}, before it was {before!r}")
    box = page.get_by_role("searchbox", name="Search people").input_value()
    ck.that(box == "", f"the search box reads {box!r}")
    return ck


@ORACLE.scenario("S4", "clicking a row opens that person, and Back returns to the list")
def open_and_back(page, ctx):
    ck = Checks()
    open_people(page, ctx)
    first = page.locator("main tbody tr").first
    name = first.inner_text().splitlines()[1].strip()  # line 0 is the avatar's initials
    first.click()
    heading = page.get_by_role("heading", level=1, name=name)
    heading.wait_for()
    ck.that(re.search(r"/people/\d+$", page.url) is not None, f"the link is {page.url}")
    ck.that(heading.is_visible(), f"the page is titled {name!r}")
    ck.note(ctx.shot(page, "people-S4"))
    page.get_by_role("link", name="Back to People").click()
    page.locator("main tbody tr").first.wait_for()
    ck.that(page.url.endswith("/people"), f"Back goes to {page.url}")
    return ck
