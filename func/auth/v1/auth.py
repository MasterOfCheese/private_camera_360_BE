import datetime
from typing import Optional
from fastapi import Depends, APIRouter, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlmodel import Session, select
from sqlalchemy.ext.asyncio import AsyncSession
from model.db_model import  User, UserPublic
from model.db_model import get_session
from passlib.context import CryptContext
import jwt


oauth_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/token")

SECRET_KEY = "AI2025"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 5

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Token(BaseModel):
    access_token: str
    token_type: str
    user: str
    
class TokenData(BaseModel):
    username: Optional[str] = None


class UserReturn(BaseModel):
    username: str
    config : Optional[bool] = None

def verify_password(plain_password, hashed_password): 
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# async def get_current_user(token: str = Depends(oauth_scheme), session: Session = Depends(get_session)):
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         username: str = payload.get("sub")
#         if username is None:
#             raise HTTPException(status_code=401, detail="Invalid authentication credentials")
#         token_data = TokenData(username=username)
#     except:
#         raise HTTPException(status_code=401, detail="Invalid authentication credentials")
#     user = session.execute(select(User).filter(User.username == token_data.username)).first()
#     if user is None:
#         raise HTTPException(status_code=404, detail="User not found")
#     return user

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
    except jwt.ExpiredSignatureError: # Bắt lỗi token hết hạn cụ thể
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError: # Bắt các lỗi JWT khác
        raise credentials_exception

    # Truy vấn người dùng từ DB bằng username trong token
    user = await session.execute(select(User).where(User.username == token_data.username))
    user = user.scalars().first() # Lấy đối tượng User đầu tiên từ kết quả truy vấn
    if user is None:
        # Quan trọng: Nếu user không tồn tại (ví dụ đã bị xóa sau khi token được cấp),
        # coi như token không hợp lệ.
        raise credentials_exception
    return user # Trả về toàn bộ đối tượng User từ DB

def create_access_token(data: dict, expires_delta: int = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_delta)
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

router = APIRouter(prefix='/v1/auth',tags=['auth'])

@router.post("/token", response_model=Token) # Sử dụng response_model=Token
async def login_for_access_token(*,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
    request: Request# Thêm dependency session
):
    
    # 1. Tìm user trong DB
    user = await session.execute(select(User).where(User.username == form_data.username))
    user = user.scalars().first() # Lấy đối tượng User đầu tiên từ kết quả truy vấn

    # 2. Kiểm tra user tồn tại và mật khẩu khớp
    if not user or not verify_password(form_data.password, user.hash_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, # Dùng 401 cho lỗi xác thực
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}, # Chuẩn OAuth2 yêu cầu header này
        )

    # 3. Tạo access token
    access_token = create_access_token(
        data={"sub": user.username}, # Dữ liệu chính là username, đưa vào claim "sub" (subject)
        expires_delta=request.app.state.config.token_expiry_minutes # Thời gian hết hạn sử dụng giá trị mặc định từ hàm create_access_token
        # Thời gian hết hạn sử dụng giá trị mặc định từ hàm create_access_token
    )

    # 4. Trả về token theo cấu trúc của class Token
    return Token(access_token=access_token, token_type="bearer", user=user.username)
@router.get("/users/me", response_model=UserReturn)
async def read_users_me(current_user: User = Depends(get_current_user)):
    # current_user đã là đối tượng User lấy từ DB thông qua get_current_user
    # FastAPI sẽ tự động chuyển đổi current_user (kiểu User)
    # thành response theo UserPublic nhờ `response_model`
    return current_user