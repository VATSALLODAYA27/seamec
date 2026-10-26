from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import staff
from ..core.assistant import answer
from ..db import get_session
from ..models import User

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class Question(BaseModel):
    question: str = Field(max_length=500)


@router.post("")
def ask(body: Question, user: User = Depends(staff), session: Session = Depends(get_session)):
    """Answer one question from MARIS's own data. Questions are not stored."""
    return answer(body.question, user, session)
