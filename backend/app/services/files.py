"""Employee photos and documents.

Files and the database can't share a transaction, so: store the file first, then write the
row; if the database write fails, delete the file. Files are deleted only after the
database change has committed.
"""

import asyncio
import io
import uuid
from collections.abc import Awaitable, Callable

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.clock import now
from app.core.config import get_settings
from app.core.errors import InvalidInput, NotFound, TooLarge
from app.core.storage import LocalStorage, signed_url
from app.models import EmployeeDocument, User
from app.schemas import DocumentOut, LinkOut, PhotoOut
from app.services.employees import get_or_404

# Allowed types are recognised by their first bytes, not the file name.
MAGIC = {
    b"%PDF-": ("application/pdf", "pdf"),
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
}
PHOTO_SIZE = 256
Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard


def detect_type(data: bytes) -> tuple[str, str]:
    for magic, kind in MAGIC.items():
        if data.startswith(magic):
            return kind
    raise InvalidInput("Only PDF, JPG and PNG files are allowed.")


def check_size(data: bytes) -> None:
    settings = get_settings()
    if not data:
        raise InvalidInput("The file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise TooLarge(f"Files can be at most {settings.max_upload_mb} MB.")


async def _save_then_write(
    storage: LocalStorage, key: str, data: bytes, write_db: Callable[[], Awaitable]
) -> object:
    await storage.put(key, data)
    try:
        return await write_db()
    except Exception:
        await storage.delete(key)
        raise


def _document_out(doc: EmployeeDocument) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        file_name=doc.file_name,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        uploaded_by_name=doc.uploader.name,
        uploaded_at=doc.uploaded_at,
    )


def _square_webp(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGB")  # drops EXIF and alpha
            side = min(image.size)
            left, top = (image.width - side) // 2, (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side))
            image = image.resize((PHOTO_SIZE, PHOTO_SIZE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, "WEBP", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise InvalidInput("This image can't be read. Try another JPG or PNG.") from exc


async def set_photo(
    db: AsyncSession, storage: LocalStorage, user: User, employee_id: int, data: bytes
) -> PhotoOut:
    employee = await get_or_404(db, employee_id)
    check_size(data)
    content_type, _ = detect_type(data)
    if content_type == "application/pdf":
        raise InvalidInput("A photo must be a JPG or PNG.")
    webp = await asyncio.to_thread(_square_webp, data)  # image work is CPU-heavy
    old_key = employee.photo_key
    new_key = f"employees/{employee.id}/photo-{uuid.uuid4().hex}.webp"

    async def write_db():
        employee.photo_key = new_key
        employee.updated_by = user.id
        await cache.bump_data_version(db)
        await db.commit()

    await _save_then_write(storage, new_key, webp, write_db)
    if old_key:
        await storage.delete(old_key)
    return PhotoOut(photo_url=signed_url(new_key, "photo.webp", "image/webp", inline=True))


async def remove_photo(
    db: AsyncSession, storage: LocalStorage, user: User, employee_id: int
) -> None:
    employee = await get_or_404(db, employee_id)
    old_key = employee.photo_key
    if old_key is None:
        return
    employee.photo_key = None
    employee.updated_by = user.id
    await cache.bump_data_version(db)
    await db.commit()
    await storage.delete(old_key)


async def list_documents(db: AsyncSession, employee_id: int) -> list[DocumentOut]:
    await get_or_404(db, employee_id)
    docs = await db.scalars(
        select(EmployeeDocument)
        .where(EmployeeDocument.employee_id == employee_id, EmployeeDocument.deleted_at.is_(None))
        .order_by(EmployeeDocument.uploaded_at.desc(), EmployeeDocument.id.desc())
    )
    return [_document_out(d) for d in docs]


def _clean_file_name(name: str | None, extension: str) -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()[:200]
    return base or f"document.{extension}"


async def upload_document(
    db: AsyncSession,
    storage: LocalStorage,
    user: User,
    employee_id: int,
    file_name: str | None,
    data: bytes,
) -> DocumentOut:
    employee = await get_or_404(db, employee_id)
    check_size(data)
    content_type, extension = detect_type(data)
    key = f"employees/{employee.id}/docs/{uuid.uuid4().hex}.{extension}"

    async def write_db() -> EmployeeDocument:
        doc = EmployeeDocument(
            employee_id=employee.id,
            file_name=_clean_file_name(file_name, extension),
            content_type=content_type,
            size_bytes=len(data),
            storage_key=key,
            uploaded_by=user.id,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)  # loads the uploader for the response
        return doc

    return _document_out(await _save_then_write(storage, key, data, write_db))


async def _get_document(db: AsyncSession, employee_id: int, doc_id: int) -> EmployeeDocument:
    doc = await db.get(EmployeeDocument, doc_id)
    if doc is None or doc.employee_id != employee_id or doc.deleted_at is not None:
        raise NotFound("Document not found.")
    return doc


async def download_link(db: AsyncSession, employee_id: int, doc_id: int) -> LinkOut:
    doc = await _get_document(db, employee_id, doc_id)
    return LinkOut(url=signed_url(doc.storage_key, doc.file_name, doc.content_type))


async def delete_document(db: AsyncSession, employee_id: int, doc_id: int) -> None:
    """Soft delete: the row stays for the record; the file is purged later."""
    doc = await _get_document(db, employee_id, doc_id)
    doc.deleted_at = now()
    await db.commit()
