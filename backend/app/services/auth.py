import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password, verify_password
from app.core.clock import now
from app.core.errors import Unauthorized
from app.models import User

# Checked when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = hash_password("not-a-real-password")


async def login(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        await asyncio.to_thread(verify_password, password, _DUMMY_HASH)
        raise Unauthorized("Wrong email or password.")
    if (
        not await asyncio.to_thread(verify_password, password, user.password_hash)
        or not user.active
    ):
        raise Unauthorized("Wrong email or password.")
    user.last_login_at = now()
    await db.commit()
    return user
