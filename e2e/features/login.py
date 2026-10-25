"""Oracle: sign-in and what each role may do. Click paths are in login.md."""

from oracle_kit import USERS, Checks, Oracle, Outcome, eventually, open_employee, submit_login

ORACLE = Oracle("login")

MISMATCH = "That email and password don't match"
MENU = ["Home", "People", "Insights", "Imports", "Salary changes", "Users"]


@ORACLE.scenario("S1", "the HR Admin signs in and sees their name and role")
def admin_signs_in(page, ctx):
    ck = Checks()
    email, _ = USERS["admin"]
    submit_login(page, ctx, email, ctx.passwords["admin"])
    nav = page.get_by_role("navigation", name="Main")
    nav.wait_for()
    menu = page.locator("aside").inner_text()
    links = nav.get_by_role("link").all_inner_texts()
    ck.that(links == MENU, f"menu links are {links}")
    ck.that("Priya Sharma" in menu and "HR Admin" in menu, f"user menu reads {menu!r}")
    add = page.get_by_role("button", name="Add employee")
    ck.that(add.count() == 0, "no Add employee on Home")
    nav.get_by_role("link", name="People").click()
    page.locator("main tbody tr").first.wait_for()
    ck.that(add.is_visible(), "Add employee is shown on People")
    ck.note(ctx.shot(page, "login-S1"))
    return ck


@ORACLE.scenario("S2", "a wrong password shows an error and stays on sign-in")
def wrong_password(page, ctx):
    ck = Checks()
    email, _ = USERS["admin"]
    submit_login(page, ctx, email, "not-the-password")
    alert = page.locator("form [role='alert']")
    alert.wait_for()
    ck.that(MISMATCH in alert.inner_text(), f"error reads {alert.inner_text()!r}")
    ck.that(page.get_by_role("navigation", name="Main").count() == 0, "the app menu is not shown")
    ck.that(page.get_by_label("Password").is_visible(), "the sign-in form is still shown")
    ck.note(ctx.shot(page, "login-S2"))
    return ck


@ORACLE.scenario("S3", "the HR Viewer sees salaries but no way to change them")
def viewer_cannot_change(page, ctx):
    ctx.sign_in(page, "viewer")
    if not open_employee(page, ctx, "ACM-000010"):
        return Outcome.skip("employee ACM-000010 is not in this database")
    ck = Checks()
    salary = page.get_by_test_id("current-salary").inner_text()
    ck.that(any(ch.isdigit() for ch in salary), f"the salary is shown: {salary!r}")
    for name in ("Change salary", "Edit details", "Mark as left", "Add employee"):
        ck.that(page.get_by_role("button", name=name).count() == 0, f"no {name!r} button")
    ck.that("HR Viewer" in page.locator("aside").inner_text(), "user menu says HR Viewer")
    ck.note(ctx.shot(page, "login-S3"))
    return ck


@ORACLE.scenario("S4", "signing out shows the sign-in page, and People needs a sign-in again")
def sign_out(page, ctx):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    ctx.sign_in(page, "admin")
    ck = Checks()
    page.get_by_role("button", name="Priya Sharma").click()
    page.get_by_role("menuitem", name="Sign out").click()
    heading = page.get_by_role("heading", name="Sign in")
    ck.that(eventually(heading.is_visible, True), "the sign-in page is shown")
    ck.that(not errors, f"no errors in the page: {errors}")
    ck.note(ctx.shot(page, "login-S4"))
    page.goto(ctx.url("/people"))
    heading.wait_for()
    app_menu = page.get_by_role("navigation", name="Main").count()
    ck.that(app_menu == 0, "People shows sign-in, not the app")
    return ck
