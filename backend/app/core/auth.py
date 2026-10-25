"""Password hashing and the current-user dependencies.

Every endpoint depends on `get_current_user`; switching to SSO later only changes how
that user is found.
"""

from typing import Annotated

import bcrypt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import Forbidden, Unauthorized
from app.models import User

SESSION_USER_KEY = "user_id"
SESSION_VERSION_KEY = "session_version"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Slow on purpose (bcrypt): call it with `asyncio.to_thread` from async code."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


async def get_current_user(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> User:
    user_id = request.session.get(SESSION_USER_KEY)
    user = await db.get(User, user_id) if user_id else None
    # A session from before the version existed counts as version 0.
    if (
        user is None
        or not user.active
        or request.session.get(SESSION_VERSION_KEY, 0) != user.session_version
    ):
        request.session.clear()
        raise Unauthorized("Please sign in.")
    request.state.user_id = user.id
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise Forbidden("Only HR Admins can change data. Your account can view only.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DB = Annotated[AsyncSession, Depends(get_db)]
