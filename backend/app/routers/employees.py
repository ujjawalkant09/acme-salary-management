import hashlib
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, UploadFile

from app.core import idempotency
from app.core.auth import DB, AdminUser, CurrentUser
from app.core.clock import today
from app.core.idempotency import IdempotencyHeader
from app.core.rate_limit import DOWNLOAD, HEAVY, READ, UPLOAD, WRITE, limiter
from app.core.storage import get_storage
from app.routers.uploads import read_upload
from app.schemas import (
    DocumentOut,
    EmployeeCreate,
    EmployeeFilters,
    EmployeeListItem,
    EmployeeListParams,
    EmployeeOut,
    EmployeeUpdate,
    Facets,
    LinkOut,
    MarkLeftIn,
    Page,
    PhotoOut,
    ReactivateIn,
    RecentSalaryChange,
    SalaryChangeIn,
    SalaryRecordOut,
)
from app.services import employees as service
from app.services import files

router = APIRouter(tags=["employees"])


@router.get("/employees", response_model=Page[EmployeeListItem])
@limiter.limit(READ)
def list_employees(
    request: Request, params: Annotated[EmployeeListParams, Query()], db: DB, _user: CurrentUser
):
    return service.list_employees(db, params)


@router.get("/employees/facets", response_model=Facets)
@limiter.limit(READ)
def facets(
    request: Request, filters: Annotated[EmployeeFilters, Query()], db: DB, _user: CurrentUser
):
    return service.facets(db, filters)


@router.get("/employees/export.csv")
@limiter.limit(HEAVY)
def export_csv(
    request: Request, filters: Annotated[EmployeeFilters, Query()], db: DB, _user: CurrentUser
):
    return Response(
        service.export_csv(db, filters),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="employees-{today()}.csv"'},
    )


@router.post("/employees", status_code=201, response_model=EmployeeOut)
@limiter.limit(WRITE)
def create_employee(
    request: Request, body: EmployeeCreate, db: DB, user: AdminUser, key: IdempotencyHeader = None
):
    return idempotency.run(
        db, user, key, "POST /employees", body,
        lambda: service.create(db, user, body), status_code=201,
    )  # fmt: skip


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
@limiter.limit(READ)
def get_employee(request: Request, employee_id: int, db: DB, _user: CurrentUser):
    return service.profile(db, service.get_or_404(db, employee_id))


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
@limiter.limit(WRITE)
def update_employee(
    request: Request, employee_id: int, body: EmployeeUpdate, db: DB, user: AdminUser
):
    return service.update(db, user, employee_id, body)


@router.post("/employees/{employee_id}/mark-left", response_model=EmployeeOut)
@limiter.limit(WRITE)
def mark_left(request: Request, employee_id: int, body: MarkLeftIn, db: DB, user: AdminUser):
    return service.mark_left(db, user, employee_id, body)


@router.post("/employees/{employee_id}/reactivate", response_model=EmployeeOut)
@limiter.limit(WRITE)
def reactivate(request: Request, employee_id: int, body: ReactivateIn, db: DB, user: AdminUser):
    return service.reactivate(db, user, employee_id, body)


@router.get("/employees/{employee_id}/salaries", response_model=list[SalaryRecordOut])
@limiter.limit(READ)
def salary_history(request: Request, employee_id: int, db: DB, _user: CurrentUser):
    return service.salary_history(db, employee_id)


@router.post("/employees/{employee_id}/salaries", status_code=201, response_model=EmployeeOut)
@limiter.limit(WRITE)
def change_salary(
    request: Request,
    employee_id: int,
    body: SalaryChangeIn,
    db: DB,
    user: AdminUser,
    key: IdempotencyHeader = None,
):
    return idempotency.run(
        db, user, key, f"POST /employees/{employee_id}/salaries", body,
        lambda: service.change_salary(db, user, employee_id, body), status_code=201,
    )  # fmt: skip


@router.get("/salary-changes/recent", response_model=list[RecentSalaryChange])
@limiter.limit(READ)
def recent_salary_changes(
    request: Request, db: DB, _user: CurrentUser, limit: Annotated[int, Query(ge=1, le=50)] = 8
):
    return service.recent_changes(db, limit)


# ---------- photo and documents ----------
@router.put("/employees/{employee_id}/photo", response_model=PhotoOut)
@limiter.limit(UPLOAD)
def set_photo(request: Request, employee_id: int, file: UploadFile, db: DB, user: AdminUser):
    data = read_upload(file)
    return files.set_photo(db, get_storage(), user, employee_id, data)


@router.delete("/employees/{employee_id}/photo", status_code=204)
@limiter.limit(WRITE)
def remove_photo(request: Request, employee_id: int, db: DB, user: AdminUser):
    files.remove_photo(db, get_storage(), user, employee_id)
    return Response(status_code=204)


@router.get("/employees/{employee_id}/documents", response_model=list[DocumentOut])
@limiter.limit(READ)
def list_documents(request: Request, employee_id: int, db: DB, _user: CurrentUser):
    return files.list_documents(db, employee_id)


@router.post("/employees/{employee_id}/documents", status_code=201, response_model=DocumentOut)
@limiter.limit(UPLOAD)
def upload_document(
    request: Request,
    employee_id: int,
    file: UploadFile,
    db: DB,
    user: AdminUser,
    key: IdempotencyHeader = None,
):
    data = read_upload(file)
    fingerprint = {"file_name": file.filename, "sha256": hashlib.sha256(data).hexdigest()}
    return idempotency.run(
        db, user, key, f"POST /employees/{employee_id}/documents", fingerprint,
        lambda: files.upload_document(db, get_storage(), user, employee_id, file.filename, data),
        status_code=201,
    )  # fmt: skip


@router.get("/employees/{employee_id}/documents/{doc_id}/download", response_model=LinkOut)
@limiter.limit(DOWNLOAD)
def download_document(request: Request, employee_id: int, doc_id: int, db: DB, _user: CurrentUser):
    return files.download_link(db, employee_id, doc_id)


@router.delete("/employees/{employee_id}/documents/{doc_id}", status_code=204)
@limiter.limit(WRITE)
def delete_document(request: Request, employee_id: int, doc_id: int, db: DB, _user: AdminUser):
    files.delete_document(db, employee_id, doc_id)
    return Response(status_code=204)
