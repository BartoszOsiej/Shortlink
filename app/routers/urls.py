import secrets
import string
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import URL, User
from app.schemas import URLOut, URLStats

router = APIRouter(prefix="/urls", tags=["urls"])

def gen_short() -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(6))

@router.post("/shorten", response_model=URLOut)
def shorten(
    target_url: str,
    expires_in_seconds: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expires_at = None
    if expires_in_seconds is not None:
        if expires_in_seconds <= 0:
            raise HTTPException(status_code=422, detail="expires_in_seconds must be positive")
        expires_at = datetime.now(timezone.utc).timestamp() + expires_in_seconds
        expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)

    short = gen_short()
    while db.query(URL).filter(URL.short_code == short).first():
        short = gen_short()
    url = URL(
        short_code=short,
        target_url=target_url,
        owner_id=user.id,
        expires_at=expires_at,
    )
    db.add(url)
    db.commit()
    db.refresh(url)
    return URLOut(id=url.id, short_code=url.short_code, target_url=url.target_url, clicks=url.clicks, is_active=url.is_active, expires_at=url.expires_at)

@router.get("/my", response_model=list[URLOut])
def my_urls(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    urls = db.query(URL).filter(URL.owner_id == user.id).order_by(URL.created_at.desc()).all()
    return [URLOut(id=u.id, short_code=u.short_code, target_url=u.target_url, clicks=u.clicks, is_active=u.is_active, expires_at=u.expires_at) for u in urls]

@router.get("/{short_code}/stats", response_model=URLStats)
def stats(short_code: str, db: Session = Depends(get_db)):
    url = db.query(URL).filter(URL.short_code == short_code).first()
    if not url:
        raise HTTPException(status_code=404)
    return URLStats(short_code=url.short_code, target_url=url.target_url, clicks=url.clicks, total=url.clicks)

@router.delete("/{short_code}", status_code=204)
def delete(short_code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    url = db.query(URL).filter(URL.short_code == short_code, URL.owner_id == user.id).first()
    if not url:
        raise HTTPException(status_code=404)
    db.delete(url)
    db.commit()

@router.get("/r/{short_code}")
def redirect(short_code: str, db: Session = Depends(get_db)):
    url = db.query(URL).filter(URL.short_code == short_code, URL.is_active == True).first()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")
    if url.expires_at is not None:
        expires_at = url.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            raise HTTPException(status_code=410, detail="URL expired")
    url.clicks += 1
    db.commit()
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=url.target_url, status_code=302)
