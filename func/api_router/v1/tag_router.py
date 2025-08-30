from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from func.auth.v1.auth import get_current_user
from model.db_model import Tag, TagCreate, TagPublic, TagUpdate, TagPublicWithCameraConfigs, UserPublic, get_session
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/tags",tags=["tags"])


@router.post("/", response_model=TagPublicWithCameraConfigs)
async def create_tag(*, session: AsyncSession = Depends(get_session), tag: TagCreate, user: UserPublic= Depends(get_current_user)):
    if hasattr(user, 'config') and user.config == False:
        raise HTTPException(status_code=403, detail="Permission denied")
    db_tag = Tag(**tag.dict())
    session.add(db_tag)
    await session.commit()
    await session.refresh(db_tag)
    return db_tag


@router.get("/{tag_id}", response_model=TagPublicWithCameraConfigs)
async def read_tag(*, session: AsyncSession = Depends(get_session), tag_id: int, user: UserPublic= Depends(get_current_user)
             ):
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


@router.get("/", response_model=list[TagPublic])
async def read_tags(
    *, session: AsyncSession = Depends(get_session), offset: int = 0, limit: int = Query(default=100, le=100), tag_name: Optional[str] = Query(default=None), user: UserPublic= Depends(get_current_user)
):
    query = select(Tag)
    if tag_name:
        query = query.where(Tag.tag_name.contains(tag_name))
    tags = await session.execute(query.offset(offset).limit(limit))
    tags = tags.scalars().all()
    return tags


@router.patch("/{tag_id}", response_model=TagPublicWithCameraConfigs)
async def update_tag(
    *, session: AsyncSession = Depends(get_session), tag_id: int, tag: TagUpdate, user: UserPublic= Depends(get_current_user)
):
    if hasattr(user, 'config') and user.config == False:
        raise HTTPException(status_code=403, detail="Permission denied")
    db_tag = await session.get(Tag, tag_id)
    if not db_tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    tag_data = tag.dict(exclude_unset=True)
    for key, value in tag_data.items():
        setattr(db_tag, key, value)
    session.add(db_tag)
    await session.commit()
    await session.refresh(db_tag)
    return db_tag


@router.delete("/{tag_id}")
async def delete_tag(
    *, session: AsyncSession = Depends(get_session), tag_id: int, user: UserPublic= Depends(get_current_user)
               ):
    if hasattr(user, 'config') and user.config == False:
        raise HTTPException(status_code=403, detail="Permission denied")
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await session.delete(tag)
    await session.commit()
    return {"ok": True}
