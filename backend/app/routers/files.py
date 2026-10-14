from urllib.parse import quote

from fastapi import APIRouter, Request, Response

from app.core.auth import CurrentUser
from app.core.rate_limit import DOWNLOAD, limiter
from app.core.storage import get_storage, read_signed

router = APIRouter(tags=["files"])


@router.get("/files/{token}")
@limiter.limit(DOWNLOAD)
def download(request: Request, token: str, _user: CurrentUser):
    """Serve a file from a short-lived signed link (made by the documents/photo endpoints)."""
    link = read_signed(token)
    disposition = "inline" if link["inline"] else "attachment"
    return Response(
        get_storage().get(link["key"]),
        media_type=link["type"],
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(link['name'])}",
            "Cache-Control": "private, max-age=900",
        },
    )
