from pydantic import BaseModel
from typing import Optional

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

class RefreshRequest(BaseModel):
    refresh_token: str

class ClientCredentialsRequest(BaseModel):
    client_id: str
    client_secret: str
    scope: Optional[str] = None

class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
