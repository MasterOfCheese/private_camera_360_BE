from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from func.auth.v1.auth import get_password_hash, get_current_user
from model.db_model import  User, UserCreate, UserPublic, UserUpdate
from sqlalchemy.ext.asyncio import AsyncSession

from model.db_model import get_session

router = APIRouter(prefix='/v1/users',tags=['users'])


@router.post("/", response_model=UserPublic)
async def create_user(*, session: AsyncSession = Depends(get_session), user: UserCreate, auth_user: UserPublic = Depends(get_current_user)):
    if auth_user.config == False:
        raise HTTPException(status_code=403, detail="Permission denied")
    user.hash_password = get_password_hash(user.hash_password)
    db_user = User(**user.dict())
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


@router.get("/", response_model=list[UserPublic])
async def read_users(
    *, session: AsyncSession = Depends(get_session), offset: int = 0, limit: int = Query(default=100, le=100), auth_user: UserPublic = Depends(get_current_user)
):
    if auth_user.config == False:
        raise HTTPException(status_code=403, detail="Permission denied")
    users = await session.execute(select(User).offset(offset).limit(limit))
    users = users.scalars().all()
    return users


@router.get("/{user_id}", response_model=UserPublic)
async def read_user(*, session: AsyncSession = Depends(get_session), user_id: int, auth_user: UserPublic = Depends(get_current_user)):
    if auth_user.config == False:
        raise HTTPException(status_code=403, detail="Permission denied")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserPublic)
async def update_user(
    *, session: AsyncSession = Depends(get_session), user_id: int, user: UserUpdate, auth_user: UserPublic = Depends(get_current_user)
):
    if auth_user.config == False:
        raise HTTPException(status_code=403, detail="Permission denied")
    db_user = await session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    user_data = user.dict(exclude_unset=True)
    if user.hash_password == db_user.hash_password:
        user_data.pop("hash_password", None)
    elif user.hash_password:
        user_data["hash_password"] = get_password_hash(user.hash_password)
    for key, value in user_data.items():
        setattr(db_user, key, value)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


@router.delete("/{user_id}")
async def delete_user(*, session: AsyncSession = Depends(get_session), user_id: int, auth_user: UserPublic = Depends(get_current_user)):
    if auth_user.config == False:
        raise HTTPException(status_code=403, detail="Permission denied")
    if user_id == auth_user.id:
        raise HTTPException(status_code=403, detail="Cannot delete yourself")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
    return {"ok": True}
    
