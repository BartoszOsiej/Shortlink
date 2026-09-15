from datetime import datetime
from typing import Optional

from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserCreate(BaseModel):
    email: str
    password: str

class UserOut(BaseModel):
    id: str
    email: str

class URLOut(BaseModel):
    id: str
    short_code: str
    target_url: str
    clicks: int
    is_active: bool
    expires_at: Optional[datetime] = None

class URLStats(BaseModel):
    short_code: str
    target_url: str
    clicks: int
    total: int
