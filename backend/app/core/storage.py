"""Private file storage (photos, documents, import uploads).

Files are never served from a public path: downloads go through short-lived signed links
(`/api/v1/files/<token>`). Local folder in development and tests; an S3 implementation of
the same three methods is added with the AWS deployment.
"""

from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings
from app.core.errors import NotFound

LINK_LIFETIME_SECONDS = 15 * 60


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise NotFound("File not found.")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFound("File not found.")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="file-link")


def signed_url(key: str, file_name: str, content_type: str, inline: bool = False) -> str:
    token = _signer().dumps({"key": key, "name": file_name, "type": content_type, "inline": inline})
    return f"/api/v1/files/{token}"


def read_signed(token: str) -> dict:
    try:
        return _signer().loads(token, max_age=LINK_LIFETIME_SECONDS)
    except SignatureExpired as exc:
        raise NotFound("This link has expired. Open the file again from the app.") from exc
    except BadSignature as exc:
        raise NotFound("File not found.") from exc
