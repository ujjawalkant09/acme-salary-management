import io
import uuid
from datetime import timedelta

import pytest
from PIL import Image

from app.core import storage as storage_module
from app.core.errors import NotFound
from app.models import EmployeeDocument
from app.services import files as service
from app.worker.tasks import purge_removed_documents

API = "/api/v1/employees"
PDF = b"%PDF-1.4\n% test document\n"


def png_bytes(size=(400, 300)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "blue").save(out, "PNG")
    return out.getvalue()


def upload(client, employee_id, data=PDF, name="contract.pdf", key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(
        f"{API}/{employee_id}/documents", files={"file": (name, data)}, headers=headers
    )


# ---------- photos ----------
def test_photo_is_cropped_to_square_webp(admin_client, make_employee, storage, db):
    e = make_employee()
    response = admin_client.put(f"{API}/{e.id}/photo", files={"file": ("me.png", png_bytes())})
    assert response.status_code == 200, response.text
    db.refresh(e)
    with Image.open(io.BytesIO(storage.get(e.photo_key))) as image:
        assert (image.format, image.size) == ("WEBP", (256, 256))
    photo = admin_client.get(response.json()["photo_url"])
    assert photo.headers["content-type"] == "image/webp"
    assert photo.headers["content-disposition"].startswith("inline")
    assert admin_client.get(f"{API}/{e.id}").json()["photo_url"]


def test_new_photo_replaces_old_file(admin_client, make_employee, storage, db):
    e = make_employee()
    admin_client.put(f"{API}/{e.id}/photo", files={"file": ("a.png", png_bytes())})
    db.refresh(e)
    old_key = e.photo_key
    admin_client.put(f"{API}/{e.id}/photo", files={"file": ("b.png", png_bytes((50, 80)))})
    db.refresh(e)
    assert e.photo_key != old_key
    with pytest.raises(NotFound):
        storage.get(old_key)


def test_remove_photo(admin_client, make_employee, db):
    e = make_employee()
    admin_client.put(f"{API}/{e.id}/photo", files={"file": ("a.png", png_bytes())})
    assert admin_client.delete(f"{API}/{e.id}/photo").status_code == 204
    assert (
        admin_client.delete(f"{API}/{e.id}/photo").status_code == 204
    )  # already gone: same end state
    db.refresh(e)
    assert e.photo_key is None


@pytest.mark.parametrize(
    ("data", "status"),
    [(PDF, 422), (b"GIF89a....", 422), (b"\x89PNG\r\n\x1a\nnot really", 422), (b"", 422)],
)
def test_bad_photos_are_rejected(admin_client, make_employee, data, status):
    e = make_employee()
    assert (
        admin_client.put(f"{API}/{e.id}/photo", files={"file": ("x.png", data)}).status_code
        == status
    )


# ---------- documents ----------
def test_upload_list_download_and_remove_document(admin_client, make_employee):
    e = make_employee()
    created = upload(admin_client, e.id, name="../../etc/Offer letter.pdf")
    assert created.status_code == 201, created.text
    doc = created.json()
    assert (doc["file_name"], doc["content_type"], doc["size_bytes"]) == (
        "Offer letter.pdf",
        "application/pdf",
        len(PDF),
    )
    assert doc["uploaded_by_name"] == "Priya Admin"
    assert [d["id"] for d in admin_client.get(f"{API}/{e.id}/documents").json()] == [doc["id"]]

    link = admin_client.get(f"{API}/{e.id}/documents/{doc['id']}/download").json()["url"]
    file = admin_client.get(link)
    assert file.content == PDF
    assert file.headers["content-disposition"].startswith("attachment")

    assert admin_client.delete(f"{API}/{e.id}/documents/{doc['id']}").status_code == 204
    assert admin_client.get(f"{API}/{e.id}/documents").json() == []
    assert admin_client.delete(f"{API}/{e.id}/documents/{doc['id']}").status_code == 404


def test_same_upload_twice_stores_one_document(admin_client, make_employee, db):
    e = make_employee()
    key = str(uuid.uuid4())
    first, second = upload(admin_client, e.id, key=key), upload(admin_client, e.id, key=key)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert db.query(EmployeeDocument).count() == 1
    assert upload(admin_client, e.id, data=PDF + b"x", key=key).status_code == 409


def test_document_type_and_size_limits(admin_client, make_employee, monkeypatch):
    e = make_employee()
    assert upload(admin_client, e.id, data=b"MZ\x90\x00 exe", name="cv.pdf").status_code == 422
    assert upload(admin_client, e.id, data=png_bytes(), name="scan.png").status_code == 201
    monkeypatch.setattr(service.get_settings(), "max_upload_mb", 0)
    too_big = upload(admin_client, e.id)
    assert too_big.status_code == 413
    assert too_big.json()["error"]["code"] == "too_large"


def test_documents_of_unknown_employee_or_other_employee(admin_client, make_employee):
    a, b = make_employee(), make_employee()
    doc = upload(admin_client, a.id).json()
    assert upload(admin_client, 9999).status_code == 404
    assert admin_client.get(f"{API}/{b.id}/documents/{doc['id']}/download").status_code == 404
    assert admin_client.get(f"{API}/9999/documents").status_code == 404


def test_failed_database_write_deletes_the_uploaded_file(
    make_employee, admin, db, storage, monkeypatch
):
    e = make_employee()
    saved = []
    real_put = storage.put
    monkeypatch.setattr(storage, "put", lambda key, data: (saved.append(key), real_put(key, data)))

    def broken_commit():
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "commit", broken_commit)
    with pytest.raises(RuntimeError):
        service.upload_document(db, storage, admin, e.id, "a.pdf", PDF)
    db.rollback()
    assert saved and not (storage.root / saved[0]).exists()


def test_file_links_expire_and_cannot_be_forged(admin_client, make_employee, monkeypatch):
    e = make_employee()
    doc = upload(admin_client, e.id).json()
    link = admin_client.get(f"{API}/{e.id}/documents/{doc['id']}/download").json()["url"]
    assert admin_client.get(link + "x").status_code == 404
    monkeypatch.setattr(storage_module, "LINK_LIFETIME_SECONDS", -1)
    expired = admin_client.get(link)
    assert expired.status_code == 404
    assert "expired" in expired.json()["error"]["message"]


def test_file_links_need_sign_in(admin_client, anon_client, make_employee):
    e = make_employee()
    doc = upload(admin_client, e.id).json()
    link = admin_client.get(f"{API}/{e.id}/documents/{doc['id']}/download").json()["url"]
    assert anon_client.get(link).status_code == 401


def test_removed_documents_are_purged_after_30_days(
    admin_client, make_employee, db, storage, frozen_clock
):
    e = make_employee()
    doc_id = upload(admin_client, e.id).json()["id"]
    admin_client.delete(f"{API}/{e.id}/documents/{doc_id}")
    assert purge_removed_documents(db, storage) == 0
    frozen_clock.set(frozen_clock.current + timedelta(days=31))
    db.expire_all()
    key = db.get(EmployeeDocument, doc_id).storage_key
    assert purge_removed_documents(db, storage) == 1
    assert not (storage.root / key).exists()
    assert purge_removed_documents(db, storage) == 0  # safe to re-run
