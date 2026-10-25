from fastapi import APIRouter, Request, Response

from app.core.auth import DB, SESSION_USER_KEY, SESSION_VERSION_KEY, CurrentUser
from app.core.rate_limit import LOGIN, READ, limiter
from app.schemas import LoginIn, UserOut
from app.services import auth as service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
@limiter.limit(LOGIN, key_func=lambda request: f"login:{request.client.host}")
async def login(request: Request, body: LoginIn, db: DB):
    user = await service.login(db, body.email, body.password)
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.id
    request.session[SESSION_VERSION_KEY] = user.session_version
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request):
    request.session.clear()
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
@limiter.limit(READ)
async def me(request: Request, user: CurrentUser):
    return user
