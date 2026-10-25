from fastapi import APIRouter, Request, Response

from app.core import idempotency
from app.core.auth import DB, AdminUser
from app.core.idempotency import IdempotencyHeader
from app.core.rate_limit import READ, WRITE, limiter
from app.schemas import PasswordIn, UserActiveIn, UserAdminOut, UserCreate, UserRoleIn
from app.services import users as service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserAdminOut])
@limiter.limit(READ)
async def list_users(request: Request, db: DB, _user: AdminUser):
    return await service.list_users(db)


@router.post("", status_code=201, response_model=UserAdminOut)
@limiter.limit(WRITE)
async def create_user(
    request: Request, body: UserCreate, db: DB, user: AdminUser, key: IdempotencyHeader = None
):
    return await idempotency.run(
        db, user, key, "POST /users", body,
        lambda: service.create_user(db, user, body), status_code=201,
    )  # fmt: skip


@router.put("/{user_id}/role", response_model=UserAdminOut)
@limiter.limit(WRITE)
async def set_role(request: Request, user_id: int, body: UserRoleIn, db: DB, user: AdminUser):
    return await service.set_role(db, user, user_id, body.role)


@router.put("/{user_id}/active", response_model=UserAdminOut)
@limiter.limit(WRITE)
async def set_active(request: Request, user_id: int, body: UserActiveIn, db: DB, user: AdminUser):
    return await service.set_active(db, user, user_id, body.active)


@router.put("/{user_id}/password", status_code=204)
@limiter.limit(WRITE)
async def reset_password(request: Request, user_id: int, body: PasswordIn, db: DB, user: AdminUser):
    await service.reset_password(db, user, user_id, body.password)
    return Response(status_code=204)


@router.delete("/{user_id}", status_code=204)
@limiter.limit(WRITE)
async def delete_user(request: Request, user_id: int, db: DB, user: AdminUser):
    await service.delete_user(db, user, user_id)
    return Response(status_code=204)
