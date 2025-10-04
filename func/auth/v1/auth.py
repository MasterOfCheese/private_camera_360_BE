# auth.py - Improved OAuth System with config.yaml
import datetime
import os
import sys
from typing import Optional, Literal
from fastapi import Depends, APIRouter, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from model.db_model import User, UserPublic, get_session, Token, UserInfo
from passlib.context import CryptContext
import jwt
import requests

# Import Config class
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import Config

oauth_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/token")

# Load config từ config.yaml
def load_oauth_config():
    """Load OAuth configuration from config.yaml"""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        config_path = os.path.join(project_root, 'config', 'config.yaml')
        
        if not os.path.exists(config_path):
            config_path = os.path.join(os.getcwd(), 'config', 'config.yaml')
        
        config_manager = Config(config_path)
        config_manager.load_config()
        config_obj = config_manager.get_config()
        
        return config_obj.to_dict()
    except Exception as e:
        print(f"Error loading OAuth config: {e}")
        # Fallback to environment variables
        return {
            'oauth': {
                'secret_key': os.getenv("SECRET_KEY", "AI2025"),
                'algorithm': 'HS256',
                'access_token_expire_minutes': 15,
                'providers': {}
            }
        }

# Load config at startup
APP_CONFIG = load_oauth_config()
OAUTH_CONFIG = APP_CONFIG.get('oauth', {})

SECRET_KEY = OAUTH_CONFIG.get('secret_key', 'AI2025')
ALGORITHM = OAUTH_CONFIG.get('algorithm', 'HS256')
ACCESS_TOKEN_EXPIRE_MINUTES = OAUTH_CONFIG.get('access_token_expire_minutes', 15)

# Build OAuth Provider Configurations from config
def build_oauth_providers():
    """Build OAuth providers configuration from config.yaml"""
    providers = {}
    config_providers = OAUTH_CONFIG.get('providers', {})
    
    for provider_name, provider_config in config_providers.items():
        if not provider_config.get('client_id') or not provider_config.get('client_secret'):
            # Skip providers without credentials
            continue
            
        providers[provider_name] = {
            "client_id": provider_config.get('client_id'),
            "client_secret": provider_config.get('client_secret'),
            "token_url": provider_config.get('token_url'),
            "user_info_url": provider_config.get('user_info_url'),
            "user_info_headers": lambda token: {"Authorization": f"Bearer {token}"} 
                if provider_name != "github" 
                else {"Authorization": f"token {token}"},
            "username_field": provider_config.get('username_field', 'username')
        }
    
    return providers

OAUTH_PROVIDERS = build_oauth_providers()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
OAUTH_DUMMY_HASH = pwd_context.hash("")

router = APIRouter(prefix='/v1/auth', tags=['auth'])

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password): 
    if hashed_password == OAUTH_DUMMY_HASH:
        return False
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: int = None):
    expire = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=expires_delta or ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    token: str = Depends(oauth_scheme), 
    session: AsyncSession = Depends(get_session)
) -> UserPublic: 
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
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_exception

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return UserPublic.from_orm(user)

# ===== Standard Login =====

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
    request: Request = None
):
    """Standard username/password login"""
    result = await session.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hash_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expiry_minutes = getattr(
        request.app.state.config, 
        'token_expiry_minutes', 
        ACCESS_TOKEN_EXPIRE_MINUTES
    ) if request else ACCESS_TOKEN_EXPIRE_MINUTES
    
    access_token = create_access_token(
        data={"sub": user.username}, 
        expires_delta=expiry_minutes
    )

    return Token(
        access_token=access_token, 
        token_type="bearer", 
        username=user.username
    )

@router.get("/users/me", response_model=UserInfo)
async def read_users_me(current_user: UserPublic = Depends(get_current_user)):
    """Get current user info"""
    return UserInfo(username=current_user.username, config=current_user.config)

# ===== OAuth Login - Unified Endpoint =====

class OAuthLoginRequest(BaseModel):
    provider: str  # Dynamic based on config.yaml
    code: str
    state: Optional[str] = None

@router.post("/oauth", response_model=Token)
async def oauth_login(
    request: OAuthLoginRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Unified OAuth login endpoint
    Supports multiple providers configured in config.yaml
    """
    provider_name = request.provider
    code = request.code

    # 1. Get provider config
    provider_config = OAUTH_PROVIDERS.get(provider_name)
    if not provider_config:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported OAuth provider: {provider_name}"
        )

    # Validate provider credentials
    if not provider_config["client_id"] or not provider_config["client_secret"]:
        raise HTTPException(
            status_code=500,
            detail=f"OAuth provider '{provider_name}' is not configured properly"
        )

    # 2. Exchange code for access token
    try:
        token_response = requests.post(
            provider_config["token_url"],
            headers={'Accept': 'application/json'},
            data={
                'client_id': provider_config["client_id"],
                'client_secret': provider_config["client_secret"],
                'code': code,
            },
            timeout=10
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"{provider_name.title()} token exchange failed: {token_response.text}"
            )

        token_data = token_response.json()
        provider_access_token = token_data.get('access_token')

        if not provider_access_token:
            error_msg = token_data.get('error_description', 'No access token received')
            raise HTTPException(status_code=400, detail=error_msg)

    except requests.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to {provider_name.title()}: {str(e)}"
        )

    # 3. Get user info from provider
    try:
        user_info_response = requests.get(
            provider_config["user_info_url"],
            headers=provider_config["user_info_headers"](provider_access_token),
            timeout=10
        )

        if user_info_response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to fetch user info from {provider_name.title()}"
            )

        user_info = user_info_response.json()
        username = user_info.get(provider_config["username_field"])

        if not username:
            raise HTTPException(
                status_code=400,
                detail=f"Username not found in {provider_name.title()} response"
            )

    except requests.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user info from {provider_name.title()}: {str(e)}"
        )

    # 4. Check if user exists in database
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User '{username}' is not registered. Please contact administrator at FAI - AI Department."
        )

    # 5. Create internal JWT token
    access_token = create_access_token(data={"sub": username})

    return Token(
        access_token=access_token,
        token_type="bearer",
        username=user.username
    )

# ===== Endpoint để list available OAuth providers =====
@router.get("/oauth/providers")
async def get_oauth_providers():
    """Get list of configured OAuth providers"""
    return {
        "providers": list(OAUTH_PROVIDERS.keys())
    }