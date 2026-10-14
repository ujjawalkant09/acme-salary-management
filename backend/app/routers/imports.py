import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response, UploadFile

from app.core import idempotency
from app.core.auth import DB, AdminUser, CurrentUser
from app.core.idempotency import IdempotencyHeader
from app.core.rate_limit import HEAVY, READ, WRITE, limiter
from app.core.storage import get_storage
from app.routers.uploads import read_upload
from app.schemas import ImportCommitIn, ImportJobOut, ImportRowOut, Page
from app.services import import_file
from app.services import imports as service

router = APIRouter(prefix="/imports", tags=["imports"])

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/template.xlsx")
@limiter.limit(WRITE)
def template(request: Request, _user: CurrentUser):
    return Response(
        import_file.template_xlsx(),
        media_type=XLSX_TYPE,
        headers={"Content-Disposition": 'attachment; filename="acme-import-template.xlsx"'},
    )


@router.post("", status_code=202, response_model=ImportJobOut)
@limiter.limit(HEAVY)
def start_import(
    request: Request, file: UploadFile, db: DB, user: AdminUser, key: IdempotencyHeader = None
):
    data = read_upload(file)
    fingerprint = {"file_name": file.filename, "sha256": hashlib.sha256(data).hexdigest()}
    return idempotency.run(
        db, user, key, "POST /imports", fingerprint,
        lambda: service.start(db, get_storage(), user, file.filename, data), status_code=202,
    )  # fmt: skip


@router.get("", response_model=Page[ImportJobOut])
@limiter.limit(READ)
def list_imports(
    request: Request,
    db: DB,
    _user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return service.list_jobs(db, page, page_size)


@router.get("/{job_id}", response_model=ImportJobOut)
@limiter.limit(READ)
def get_import(request: Request, job_id: str, db: DB, _user: CurrentUser):
    return service.job_out(db, service.get_job(db, job_id))


@router.get("/{job_id}/rows", response_model=Page[ImportRowOut])
@limiter.limit(READ)
def import_rows(
    request: Request,
    job_id: str,
    db: DB,
    _user: CurrentUser,
    action: Literal["create", "update", "unchanged", "error"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return service.list_rows(db, job_id, action, page, page_size)


@router.get("/{job_id}/errors.csv")
@limiter.limit(HEAVY)
def errors_csv(request: Request, job_id: str, db: DB, _user: CurrentUser):
    return Response(
        service.errors_csv(db, job_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="import-problems-{job_id[:8]}.csv"'},
    )


@router.post("/{job_id}/commit", response_model=ImportJobOut)
@limiter.limit(HEAVY)
def commit_import(
    request: Request,
    job_id: str,
    body: ImportCommitIn,
    db: DB,
    user: AdminUser,
    key: IdempotencyHeader = None,
):
    return idempotency.run(
        db, user, key, f"POST /imports/{job_id}/commit", body,
        lambda: service.request_commit(db, job_id, body.mode),
    )  # fmt: skip


@router.post("/{job_id}/cancel", response_model=ImportJobOut)
@limiter.limit(HEAVY)
def cancel_import(request: Request, job_id: str, db: DB, _user: AdminUser):
    return service.cancel(db, get_storage(), job_id)
