from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.core import idempotency
from app.core.auth import get_current_user
from app.core.clock import now
from app.core.errors import Forbidden, Unauthorized
from app.models import IdempotencyKey, User
from app.schemas import UserCreate
from app.services import users as service
from tests.conftest import count

API = "/api/v1/users"

NEW = {
    "name": "Meera Iyer",
    "email": "Meera.Iyer@acme.example",
    "role": "hr_viewer",
    "password": "a-long-first-password",
}


async def test_admin_adds_a_viewer_who_can_then_sign_in(admin_client, anon_client):
    response = admin_client.post(API, json=NEW)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "meera.iyer@acme.example"
    assert (body["role"], body["active"]) == ("hr_viewer", True)
    assert "password" not in body and "password_hash" not in body
    login = anon_client.post(
        "/api/v1/auth/login", json={"email": NEW["email"], "password": NEW["password"]}
    )
    assert login.status_code == 200
    assert login.json()["role"] == "hr_viewer"


async def test_admin_can_add_another_admin(admin_client, db, admin):
    response = admin_client.post(API, json={**NEW, "role": "hr_admin"})
    assert response.json()["role"] == "hr_admin"
    created = await db.get(User, response.json()["id"])
    assert created.created_by == admin.id  # the audit is saved


async def test_viewers_cannot_list_or_add_users(viewer_client, db):
    assert viewer_client.get(API).status_code == 403
    assert viewer_client.post(API, json=NEW).status_code == 403
    assert await count(db, User) == 2  # nobody was added


def test_signed_out_people_get_401(anon_client):
    assert anon_client.get(API).status_code == 401


def test_an_email_in_use_is_refused_whatever_its_case(admin_client):
    response = admin_client.post(API, json={**NEW, "email": "ADMIN@acme.example"})
    assert response.status_code == 409
    assert "email" in response.json()["error"]["details"]["fields"]


def test_bad_input_is_refused(admin_client):
    for bad in (
        {"role": "superuser"},
        {"password": "shortp"},
        {"email": "not-an-email"},
        {"name": "   "},
    ):
        assert admin_client.post(API, json={**NEW, **bad}).status_code == 422, bad


def test_a_double_click_adds_one_user(admin_client):
    headers = {"Idempotency-Key": "add-meera"}
    first = admin_client.post(API, json=NEW, headers=headers)
    second = admin_client.post(API, json=NEW, headers=headers)
    assert second.status_code == 201 and second.json() == first.json()  # not a 409


def test_the_same_key_with_another_body_is_refused(admin_client):
    headers = {"Idempotency-Key": "add-meera"}
    admin_client.post(API, json=NEW, headers=headers)
    response = admin_client.post(API, json={**NEW, "name": "Someone Else"}, headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "idempotency_key_reused"


def _commit_meera_after_the_email_check(db, session_factory, monkeypatch, key=None, admin_id=None):
    """Makes another request add Meera between our email check and our insert."""
    real_scalar = db.scalar

    async def check_then_lose_the_race(query):
        found = await real_scalar(query)
        async with session_factory() as other:
            other.add(User(email=NEW["email"].lower(), name="Meera Iyer", role="hr_viewer",
                           password_hash="x"))  # fmt: skip
            await other.flush()
            if key:
                other.add(IdempotencyKey(key=key, user_id=admin_id, endpoint="POST /users",
                                         request_hash=idempotency.request_hash(UserCreate(**NEW)),
                                         status_code=201, response_body={"id": 7},
                                         expires_at=now() + timedelta(hours=1)))  # fmt: skip
            await other.commit()
        return found

    monkeypatch.setattr(db, "scalar", check_then_lose_the_race)


async def test_a_double_click_racing_itself_gets_the_first_response(
    db, admin, session_factory, monkeypatch
):
    admin_id = admin.id
    body = UserCreate(**NEW)
    _commit_meera_after_the_email_check(db, session_factory, monkeypatch, "k1", admin_id)
    response = await idempotency.run(
        db, admin, "k1", "POST /users", body,
        lambda: service.create_user(db, admin, body), status_code=201,
    )  # fmt: skip
    assert (response.status_code, response.body) == (201, b'{"id":7}')
    monkeypatch.undo()
    assert await count(db, User, email=NEW["email"].lower()) == 1  # ours was rolled back
    assert await count(db, User, created_by=admin_id) == 0


async def test_two_admins_adding_the_same_email_at_once_save_one(
    db, admin, session_factory, monkeypatch
):
    _commit_meera_after_the_email_check(db, session_factory, monkeypatch)
    with pytest.raises(IntegrityError):  # the app's handler answers it with 409
        await service.create_user(db, admin, UserCreate(**NEW))
    await db.rollback()
    monkeypatch.undo()
    assert await count(db, User, email=NEW["email"].lower()) == 1


def test_the_list_never_shows_passwords(admin_client):
    users = admin_client.get(API).json()
    assert [u["name"] for u in users] == ["Arjun Viewer", "Priya Admin"]  # sorted by name
    assert all("password_hash" not in u for u in users)


# ---------- change role, disable, reset password, delete ----------
LOGIN = "/api/v1/auth/login"
VIEWER_LOGIN = {"email": "viewer@acme.example", "password": "viewer-pass"}


def test_admin_makes_a_viewer_an_admin_and_back(admin_client, viewer_client, viewer):
    url = f"{API}/{viewer.id}/role"
    first = admin_client.put(url, json={"role": "hr_admin"})
    second = admin_client.put(url, json={"role": "hr_admin"})  # a repeat changes nothing more
    assert first.status_code == second.status_code == 200
    assert second.json()["role"] == "hr_admin"
    assert viewer_client.get(API).status_code == 200  # the new role counts at once

    assert admin_client.put(url, json={"role": "hr_viewer"}).json()["role"] == "hr_viewer"
    assert viewer_client.get(API).status_code == 403


async def test_disabling_signs_them_out_and_enabling_lets_them_sign_in_again(
    admin_client, viewer_client, anon_client, viewer, db
):
    url = f"{API}/{viewer.id}/active"
    first = admin_client.put(url, json={"active": False})
    second = admin_client.put(url, json={"active": False})
    assert first.status_code == second.status_code == 200
    assert second.json()["active"] is False
    assert viewer_client.get("/api/v1/auth/me").status_code == 401
    assert anon_client.post(LOGIN, json=VIEWER_LOGIN).status_code == 401
    await db.refresh(viewer)
    assert viewer.session_version == 1  # bumped once, not once per repeat

    assert admin_client.put(url, json={"active": True}).json()["active"] is True
    assert viewer_client.get("/api/v1/auth/me").status_code == 401  # the old session stays ended
    assert anon_client.post(LOGIN, json=VIEWER_LOGIN).status_code == 200


def test_a_password_reset_replaces_the_password_and_signs_them_out(
    admin_client, viewer_client, anon_client, viewer
):
    url = f"{API}/{viewer.id}/password"
    for _ in range(2):  # a repeat leaves the same password in place
        assert admin_client.put(url, json={"password": "a-new-password"}).status_code == 204
    assert viewer_client.get("/api/v1/auth/me").status_code == 401
    assert anon_client.post(LOGIN, json=VIEWER_LOGIN).status_code == 401
    new_login = {**VIEWER_LOGIN, "password": "a-new-password"}
    assert anon_client.post(LOGIN, json=new_login).status_code == 200


def test_a_reset_password_must_be_8_to_200_characters(admin_client, viewer):
    url = f"{API}/{viewer.id}/password"
    assert admin_client.put(url, json={"password": "1234567"}).status_code == 422
    assert admin_client.put(url, json={"password": "x" * 201}).status_code == 422
    assert admin_client.put(url, json={"password": "12345678"}).status_code == 204


async def test_an_account_that_changed_nothing_can_be_deleted(admin_client, db):
    meera = admin_client.post(API, json=NEW).json()
    assert admin_client.delete(f"{API}/{meera['id']}").status_code == 204
    assert admin_client.delete(f"{API}/{meera['id']}").status_code == 404  # already gone
    assert await count(db, User, id=meera["id"]) == 0


async def test_an_account_with_history_is_kept_and_disabling_is_offered(admin_client, db, viewer):
    # The viewer added an account, so "added by" must keep pointing at them.
    db.add(User(email="x@acme.example", name="X", role="hr_viewer", password_hash="x",
                created_by=viewer.id))  # fmt: skip
    await db.commit()
    response = admin_client.delete(f"{API}/{viewer.id}")
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "user_has_history"
    assert await count(db, User, id=viewer.id) == 1  # rolled back, nothing removed


def test_nobody_changes_their_own_account(admin_client, admin):
    for method, path, body in (
        ("PUT", "role", {"role": "hr_viewer"}),
        ("PUT", "active", {"active": False}),
        ("PUT", "password", {"password": "a-new-password"}),
        ("DELETE", "", None),
    ):
        url = f"{API}/{admin.id}/{path}".rstrip("/")
        assert admin_client.request(method, url, json=body).status_code == 403, path
    assert admin_client.get("/api/v1/auth/me").json()["role"] == "hr_admin"


def test_changing_a_user_who_does_not_exist_is_404(admin_client):
    assert admin_client.put(f"{API}/999/role", json={"role": "hr_admin"}).status_code == 404
    assert admin_client.put(f"{API}/999/active", json={"active": False}).status_code == 404
    assert admin_client.put(f"{API}/999/password", json={"password": "12345678"}).status_code == 404
    assert admin_client.delete(f"{API}/999").status_code == 404


def test_bad_role_or_active_values_are_refused(admin_client, viewer):
    assert admin_client.put(f"{API}/{viewer.id}/role", json={"role": "owner"}).status_code == 422
    assert admin_client.put(f"{API}/{viewer.id}/active", json={}).status_code == 422


def test_viewers_and_signed_out_people_cannot_manage_users(viewer_client, anon_client, admin):
    for client, status in ((viewer_client, 403), (anon_client, 401)):
        assert (
            client.put(f"{API}/{admin.id}/role", json={"role": "hr_viewer"}).status_code == status
        )
        assert client.put(f"{API}/{admin.id}/active", json={"active": False}).status_code == status
        assert (
            client.put(f"{API}/{admin.id}/password", json={"password": "12345678"}).status_code
            == status
        )
        assert client.delete(f"{API}/{admin.id}").status_code == status


async def test_an_admin_demoted_meanwhile_can_no_longer_change_others(
    db, admin, viewer, session_factory
):
    admin_id, viewer_id = admin.id, viewer.id
    # Another admin demotes this one after their request passed the admin check...
    async with session_factory() as other:
        await other.execute(update(User).where(User.id == admin_id).values(role="hr_viewer"))
        await other.commit()
    # ...so the locked re-read refuses, and two admins can't demote each other at once.
    with pytest.raises(Forbidden):
        await service.set_role(db, admin, viewer_id, "hr_admin")
    await db.rollback()
    assert (await db.get(User, viewer_id)).role == "hr_viewer"


async def test_a_session_from_before_session_versions_still_works(db, admin):
    request = SimpleNamespace(session={"user_id": admin.id}, state=SimpleNamespace())
    assert await get_current_user(request, db) is admin

    request.session["session_version"] = 1  # a version the user no longer has
    with pytest.raises(Unauthorized):
        await get_current_user(request, db)
    assert request.session == {}  # cleared, so the browser forgets it
