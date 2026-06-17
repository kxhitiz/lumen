from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..database import get_db
from ..models import Event, Org

router = APIRouter()


class EventPayload(BaseModel):
    event: str
    properties: Optional[dict[str, Any]] = {}
    user: Optional[str] = None
    project: Optional[str] = None
    timestamp: Optional[datetime] = None


def resolve_org(authorization: str = Header(...), db: Session = Depends(get_db)) -> Org:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Expected Bearer token")
    api_key = authorization.removeprefix("Bearer ").strip()
    org = db.query(Org).filter(Org.api_key == api_key).first()
    if not org:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return org


@router.delete("/events", status_code=200)
def clear_events(org: Org = Depends(resolve_org), db: Session = Depends(get_db)):
    db.query(Event).filter(Event.org_id == org.id).delete()
    db.commit()
    return {"ok": True}


@router.post("/events", status_code=201)
def ingest(payload: EventPayload, org: Org = Depends(resolve_org), db: Session = Depends(get_db)):
    event = Event(
        org_id=org.id,
        event=payload.event,
        properties=payload.properties or {},
        user=payload.user,
        project=payload.project,
        timestamp=payload.timestamp or datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    return {"ok": True}
