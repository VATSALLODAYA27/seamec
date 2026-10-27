"""Documents kept against a record: charter parties and addenda on contracts, quotes on tenders and dry docks,
policy wordings, agency accounts. Uploading a title that already exists adds a new version.

Files are stored under var/documents by their SHA-256, so a name sent by the browser never becomes a path, and are
always downloaded as attachments of an allowed type, so a file cannot run as a page in MARIS.
"""
import base64
import binascii
import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..auth import audit, manager, staff
from ..db import get_session
from ..models import Document, User, as_dict
from ..schemas import DocumentIn
from .fleet import get_or_404

router = APIRouter(prefix="/api/documents", tags=["documents"], dependencies=[Depends(staff)])

MAX_BYTES = 10 * 1024 * 1024
TYPES = {"pdf": "application/pdf", "doc": "application/msword", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "xls": "application/vnd.ms-excel", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "txt": "text/plain", "msg": "application/vnd.ms-outlook", "eml": "message/rfc822"}
STORE = config.VAR_DIR / "documents"


def store(data: bytes) -> str:
    """Keep the file under its SHA-256 and return that name. The same file uploaded twice is stored once."""
    digest = hashlib.sha256(data).hexdigest()
    STORE.mkdir(parents=True, exist_ok=True)
    if not (STORE / digest).exists():
        (STORE / digest).write_bytes(data)
    return digest


@router.get("")
def list_documents(entity: str, key: str, session: Session = Depends(get_session)):
    rows = session.scalars(select(Document).where(Document.entity == entity, Document.entity_key == key).order_by(Document.title, Document.version.desc())).all()
    latest = {}
    for d in rows:
        latest.setdefault(d.title, d.version)
    return [{**as_dict(d), "latest": latest[d.title] == d.version} for d in rows]


def counts(session: Session, entity: str, kind: str | None = None) -> dict[str, int]:
    """How many documents each record of `entity` has (optionally of one kind)."""
    q = select(Document.entity_key, func.count()).where(Document.entity == entity).group_by(Document.entity_key)
    if kind:
        q = q.where(Document.kind == kind)
    return dict(session.execute(q).all())


@router.post("", status_code=201)
def upload(body: DocumentIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    ext = body.filename.rsplit(".", 1)[-1].lower() if "." in body.filename else ""
    if ext not in TYPES:
        raise HTTPException(422, f"Allowed file types: {', '.join(sorted(TYPES))}.")
    try:
        data = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "The file could not be read.")
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(422, "The file must be between 1 byte and 10 MB.")
    digest = store(data)
    version = (session.scalar(select(func.max(Document.version)).where(Document.entity == body.entity, Document.entity_key == body.entity_key,
                                                                       Document.title == body.title.strip())) or 0) + 1
    safe_name = re.sub(r"[^\w.\- ]", "_", body.filename)[:160]
    doc = Document(entity=body.entity, entity_key=body.entity_key, kind=body.kind, title=body.title.strip(), version=version, filename=safe_name,
                   content_type=TYPES[ext], size=len(data), sha256=digest, note=body.note.strip(), uploaded_by=user.username)
    session.add(doc)
    audit(session, user, "document.uploaded", f"{body.entity} {body.entity_key}", f"{doc.title} v{version} ({safe_name})")
    session.commit()
    return as_dict(doc)


@router.get("/{doc_id}/file")
def download(doc_id: int, session: Session = Depends(get_session)):
    doc = get_or_404(session, Document, doc_id, "Document")
    path = STORE / doc.sha256
    if not path.is_file():
        raise HTTPException(410, "The stored file is missing.")
    return FileResponse(path, media_type=doc.content_type, filename=doc.filename, headers={"X-Content-Type-Options": "nosniff"})
