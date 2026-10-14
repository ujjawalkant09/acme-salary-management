"""Oracle: changing a salary, including a retried save and two people editing at once.
S1-S3 change data, so they run only with ORACLE_ALLOW_WRITES=1. Click paths: salary.md."""

import re
from decimal import Decimal

from oracle_kit import Checks, Oracle, Outcome, eventually, open_employee, salary_history

ORACLE = Oracle("salary")

SAVED = "Salary change saved"
OFFLINE = "Can't reach the server"
CONFLICT = re.compile("changed by someone else")
SALARIES_API = "**/api/v1/employees/*/salaries"


def open_as_admin(page, ctx, code) -> Outcome | None:
    """Opens the employee as the HR Admin; a SKIP when the database lacks them."""
    ctx.sign_in(page, "admin")
    if not open_employee(page, ctx, code):
        return Outcome.skip(f"employee {code} is not in this database")
    return None


def shown_salary(page) -> int:
    """The current yearly salary on the page, in whole units ("₹15,10,000" -> 1510000)."""
    return int(re.sub(r"\D", "", page.get_by_test_id("current-salary").inner_text()))


def start_change(page):
    """Opens Change salary; returns the dialog and the salary it starts from."""
    page.get_by_role("button", name="Change salary").click()
    dialog = page.get_by_role("dialog")
    amount = dialog.get_by_label(re.compile("^New yearly salary"))
    return dialog, Decimal(amount.input_value())


def submit_change(dialog, amount) -> None:
    dialog.get_by_label(re.compile("^New yearly salary")).fill(str(amount))
    dialog.get_by_label("Reason").select_option(label="Merit")
    dialog.get_by_role("button", name="Save salary change").click()


@ORACLE.scenario("S1", "the HR Admin raises a salary and sees it on the page and in the history")
def change_salary(page, ctx):
    stop = ctx.writes_refused() or open_as_admin(page, ctx, "ACM-000101")
    if stop:
        return stop
    ck = Checks()
    rows_before = salary_history(page).count()
    dialog, current = start_change(page)
    new = int(current) + 1000
    submit_change(dialog, new)
    page.get_by_text(SAVED).wait_for()
    ck.that(eventually(lambda: dialog.count(), 0) == 0, "the dialog closed")
    shown = eventually(lambda: shown_salary(page), new)
    ck.that(shown == new, f"the page shows {shown}, expected {new}")
    rows = eventually(lambda: salary_history(page).count(), rows_before + 1)
    ck.that(rows == rows_before + 1, f"history has {rows} rows, expected {rows_before + 1}")
    newest = salary_history(page).first.inner_text()
    ck.that("Merit" in newest and "Priya Sharma" in newest, f"the newest row reads {newest!r}")
    ck.note(ctx.shot(page, "salary-S1"))
    return ck


@ORACLE.scenario("S2", "the answer to a save is lost, Save again records the change once")
def retried_save(page, ctx):
    stop = ctx.writes_refused() or open_as_admin(page, ctx, "ACM-000102")
    if stop:
        return stop
    posts = []

    def lose_first_answer(route):
        if route.request.method != "POST":
            route.continue_()
            return
        posts.append(route.request.headers.get("idempotency-key"))
        if len(posts) == 1:
            route.fetch()  # the server saves the change...
            route.abort("connectionreset")  # ...but its answer never reaches the browser
        else:
            route.continue_()

    page.route(SALARIES_API, lose_first_answer)
    ck = Checks()
    rows_before = salary_history(page).count()
    dialog, current = start_change(page)
    new = int(current) + 1000
    submit_change(dialog, new)
    page.get_by_text(OFFLINE).wait_for()
    ck.that(dialog.is_visible(), "the dialog stays open after the lost answer")
    with page.expect_response(lambda r: r.request.method == "POST") as retry:
        dialog.get_by_role("button", name="Save salary change").click()
    status = retry.value.status
    ck.that(status == 201, f"Save again is answered {status}, expected 201 (the stored answer)")
    ck.that(len(posts) == 2, f"the browser sent {len(posts)} saves, expected 2")
    one_key = len(set(posts)) == 1 and posts[0] is not None
    ck.that(one_key, f"both saves carry one Idempotency-Key: {posts}")
    rows = eventually(lambda: salary_history(page).count(), rows_before + 1)
    ck.that(rows == rows_before + 1, f"history has {rows} rows, expected {rows_before + 1}")
    ck.that(shown_salary(page) == new, f"the page shows {shown_salary(page)}, expected {new}")
    ck.note(ctx.shot(page, "salary-S2"))
    return ck


@ORACLE.scenario("S3", "two admins edit at once: the second save is refused, nothing overwritten")
def concurrent_edit(page, ctx):
    stop = ctx.writes_refused() or open_as_admin(page, ctx, "ACM-000103")
    if stop:
        return stop
    other = ctx.new_page()
    open_as_admin(other, ctx, "ACM-000103")
    ck = Checks()
    rows_before = salary_history(page).count()

    dialog, current = start_change(page)
    first = int(current) + 1000
    submit_change(dialog, first)
    page.get_by_text(SAVED).wait_for()

    stale_dialog, _ = start_change(other)  # this page still holds the old version
    with other.expect_response(lambda r: r.request.method == "POST") as answer:
        submit_change(stale_dialog, int(current) + 5000)
    status = answer.value.status
    ck.that(status == 409, f"the second save is answered {status}, expected 409")
    if status == 409:
        message = other.get_by_text(CONFLICT)
        message.wait_for()
        ck.that(message.is_visible(), f"the second admin is told: {message.inner_text()!r}")
    ck.note(ctx.shot(other, "salary-S3-conflict"))

    other.reload()
    salary_history(other).first.wait_for()
    ck.that(shown_salary(other) == first, f"after reload: {shown_salary(other)}, kept {first}")
    rows = salary_history(other).count()
    ck.that(rows == rows_before + 1, f"history has {rows} rows, expected {rows_before + 1}")
    return ck


@ORACLE.scenario("S4", "a zero or non-numeric salary is refused before anything is sent")
def invalid_amount(page, ctx):
    stop = open_as_admin(page, ctx, "ACM-000104")
    if stop:
        return stop
    posts = []
    page.on("request", lambda r: r.method == "POST" and "/salaries" in r.url and posts.append(r))
    ck = Checks()
    dialog, _ = start_change(page)
    for amount, expected in (("0", "must be more than 0"), ("12abc", "Use numbers only")):
        submit_change(dialog, amount)
        error = dialog.locator("#amount-error")
        error.wait_for()
        ck.that(expected in error.inner_text(), f"{amount!r}: error reads {error.inner_text()!r}")
    ck.that(dialog.is_visible(), "the dialog stays open")
    ck.that(not posts, f"{len(posts)} saves reached the network, expected none")
    ck.note(ctx.shot(page, "salary-S4"))
    return ck
