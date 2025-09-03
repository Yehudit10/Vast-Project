from dotenv import load_dotenv
load_dotenv()  

import os
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()
API_TOKEN = os.getenv("API_TOKEN", "dev-token")

def require_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.scheme != "Bearer" or credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
