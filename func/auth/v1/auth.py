import datetime
import os
import base64
from typing import Optional
from fastapi import Depends, APIRouter, HTTPException, Request, status, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from model.db_model import User, UserPublic, get_session
from passlib.context import CryptContext
import jwt
import requests
from dotenv import load_dotenv
from urllib.parse import urlparse, urlencode

load_dotenv()

oauth_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/token")

SECRET_KEY = os.getenv("SECRET_KEY", "AI2025")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "ov23lipbkAa7YQYhp0eX")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "bdba6816d2909d0fec3012ce7f6d66acfd7d7bf7")
GITHUB_REDIRECT_URI = "http://localhost:8005/v1/auth/github/callback"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
OAUTH_DUMMY_HASH = pwd_context.hash("")

class Token(BaseModel):
    access_token: str
    token_type: str
    user: str

class TokenData(BaseModel):
    username: Optional[str] = None

class UserReturn(BaseModel):
    username: str
    config: Optional[bool] = None

def verify_password(plain_password, hashed_password): 
    if hashed_password == OAUTH_DUMMY_HASH:
        return False
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

async def get_current_user(token: str = Depends(oauth_scheme), session: AsyncSession = Depends(get_session)) -> UserPublic: 
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_exception

    result = await session.execute(select(User).where(User.username == token_data.username))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return UserPublic.from_orm(user)

def create_access_token(data: dict, expires_delta: int = None):
    expire = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=expires_delta or ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

router = APIRouter(prefix='/v1/auth', tags=['auth'])

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
    request: Request = None
):
    result = await session.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hash_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expiry_minutes = getattr(request.app.state.config, 'token_expiry_minutes', ACCESS_TOKEN_EXPIRE_MINUTES) if request else ACCESS_TOKEN_EXPIRE_MINUTES
    access_token = create_access_token(data={"sub": user.username}, expires_delta=expiry_minutes)

    return Token(access_token=access_token, token_type="bearer", user=user.username)

@router.get("/users/me", response_model=UserReturn)
async def read_users_me(current_user: UserPublic = Depends(get_current_user)):
    return {"username": current_user.username, "config": current_user.config}

@router.get("/github")
async def github_login(return_to: str = Query(...)):
    state = base64.urlsafe_b64encode(return_to.encode('utf-8')).decode('utf-8').rstrip('=')
    params = urlencode({
        'client_id': GITHUB_CLIENT_ID,
        'redirect_uri': GITHUB_REDIRECT_URI,
        'scope': 'user',
        'state': state
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")

@router.get("/github/callback")
async def github_callback(code: str = Query(...), state: str = Query(...), session: AsyncSession = Depends(get_session)):
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")

    # Decode state
    try:
        padded_state = state + '=' * (4 - len(state) % 4)
        return_to = base64.urlsafe_b64decode(padded_state).decode('utf-8')
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid state")

    # Exchange code for GitHub token
    token_resp = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={'Accept': 'application/json'},
        data={
            'client_id': GITHUB_CLIENT_ID,
            'client_secret': GITHUB_CLIENT_SECRET,
            'code': code
        }
    )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"GitHub token exchange failed: {token_resp.status_code}")

    gh_token = token_resp.json().get('access_token')
    if not gh_token:
        raise HTTPException(status_code=400, detail="No access token received")

    # Get GitHub user info
    user_resp = requests.get(
        "https://api.github.com/user",
        headers={'Authorization': f'token {gh_token}'}
    )
    if user_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch user info")

    username = user_resp.json()['login']

    # Check if user exists - REJECT if not
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The account not registered in system. Please contact Nam đẹp trai to register."
        )

    # Create internal token and redirect (only if user exists)
    access_token = create_access_token(data={"sub": username})
    parsed = urlparse(return_to)
    hash_path = parsed.fragment or '/'
    query_string = urlencode({'auth_token': access_token, 'username': username})
    redirect_url = f"{parsed.scheme}://{parsed.netloc}/#{hash_path}?{query_string}"
    
    return RedirectResponse(redirect_url, status_code=302)