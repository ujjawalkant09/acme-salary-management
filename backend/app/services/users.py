import asyncio

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.core.errors import Conflict, Forbidden, NotFound
from app.models import User
from app.schemas import UserAdminOut, UserCreate


async def list_users(db: AsyncSession) -> list[UserAdminOut]:
    users = await db.scalars(select(User).order_by(User.name))
    return [UserAdminOut.model_validate(u) for u in users]


async def create_user(db: AsyncSession, admin: User, data: UserCreate) -> UserAdminOut:
    email = data.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise Conflict(
            "Someone already signs in with this email.",
            {"fields": {"email": "Already used by another user"}},
        )
    password_hash = await asyncio.to_thread(hash_password, data.password)

    # A request that adds the same email after the check above trips the unique index.
    # The IntegrityError is left to rise: `idempotency.run` turns it into a replay when it
    # was the same request sent twice, and the app's handler answers 409 otherwise.
    user = User(
        email=email,
        name=data.name,
        role=data.role,
        password_hash=password_hash,
        created_by=admin.id,
    )
    db.add(user)
    await db.flush()
    out = UserAdminOut.model_validate(user)
    await db.commit()
    return out


async def set_role(db: AsyncSession, admin: User, user_id: int, role: str) -> UserAdminOut:
    user = await _other_user(db, admin, user_id)
    user.role = role
    out = UserAdminOut.model_validate(user)
    await db.commit()
    return out


async def set_active(db: AsyncSession, admin: User, user_id: int, active: bool) -> UserAdminOut:
    user = await _other_user(db, admin, user_id)
    if user.active and not active:
        # Ends their sessions, so enabling the account later doesn't bring them back.
        user.session_version += 1
    user.active = active
    out = UserAdminOut.model_validate(user)
    await db.commit()
    return out


async def reset_password(db: AsyncSession, admin: User, user_id: int, password: str) -> None:
    user = await _other_user(db, admin, user_id)
    user.password_hash = await asyncio.to_thread(hash_password, password)
    user.session_version += 1  # signs them out everywhere
    await db.commit()


async def delete_user(db: AsyncSession, admin: User, user_id: int) -> None:
    """Only for an account that never changed anything; others are disabled instead."""
    await _other_user(db, admin, user_id)
    try:
        await db.execute(delete(User).where(User.id == user_id))
    except IntegrityError:
        # A salary entry, employee, document, import, key or user still points at them.
        await db.rollback()
        raise Conflict(
            "This user has changed data, so the record of who did it must stay. "
            "Disable the account instead.",
            {"reason": "user_has_history"},
        ) from None
    await db.commit()


async def _other_user(db: AsyncSession, admin: User, user_id: int) -> User:
    """Loads the user to change, locking it and the acting admin's row until commit.

    Nobody can change their own account here, so the acting admin always stays an active
    admin. The lock and re-check cover two admins demoting or disabling each other at the
    same moment: the second one waits, then finds they are no longer an admin.
    """
    if user_id == admin.id:
        raise Forbidden("You can't change your own account. Ask another HR Admin.")
    admin_id = admin.id
    rows = await db.scalars(
        select(User)
        .where(User.id.in_((admin_id, user_id)))
        .order_by(User.id)  # the same lock order everywhere, so two requests can't deadlock
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    users = {u.id: u for u in rows}
    acting = users.get(admin_id)
    if acting is None or not acting.active or not acting.is_admin:
        raise Forbidden("Only HR Admins can change data. Your account can view only.")
    if user_id not in users:
        raise NotFound("User not found.")
    return users[user_id]
