from fastapi import UploadFile

from app.core.config import get_settings
from app.services.files import check_size


async def read_upload(file: UploadFile) -> bytes:
    """Read at most one byte over the limit, so a huge upload is never held in memory."""
    data = await file.read(get_settings().max_upload_bytes + 1)
    check_size(data)
    return data
