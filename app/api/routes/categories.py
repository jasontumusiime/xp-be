import uuid
from typing import Any
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from pydantic import BaseModel

from app.api.deps import SessionDep, require_roles
from app.models import Category, CategoryPublic, SubCategory, SubCategoryPublic, UserRole

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class SubCategoryCreate(BaseModel):
    name: str
    description: str | None = None
    category_id: uuid.UUID


class SubCategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class CategoriesPublic(BaseModel):
    data: list[CategoryPublic]
    count: int


class SubCategoriesPublic(BaseModel):
    data: list[SubCategoryPublic]
    count: int


# ── Categories ────────────────────────────────────────────

@router.get("/", response_model=CategoriesPublic)
def list_categories(session: SessionDep, active_only: bool = False) -> Any:
    q = select(Category).order_by(Category.name)
    if active_only:
        q = q.where(Category.is_active == True)  # noqa: E712
    items = session.exec(q).all()
    return CategoriesPublic(data=[CategoryPublic.model_validate(c) for c in items], count=len(items))


@router.post("/", response_model=CategoryPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_category(*, session: SessionDep, body: CategoryCreate) -> Any:
    if session.exec(select(Category).where(Category.name == body.name)).first():
        raise HTTPException(status_code=409, detail="Category already exists.")
    category = Category(name=body.name, description=body.description)
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def update_category(*, session: SessionDep, category_id: uuid.UUID, body: CategoryUpdate) -> Any:
    category = session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


# ── SubCategories ─────────────────────────────────────────

@router.get("/subcategories", response_model=SubCategoriesPublic)
def list_subcategories(session: SessionDep, category_id: uuid.UUID | None = None, active_only: bool = False) -> Any:
    q = select(SubCategory).order_by(SubCategory.name)
    if category_id:
        q = q.where(SubCategory.category_id == category_id)
    if active_only:
        q = q.where(SubCategory.is_active == True)  # noqa: E712
    items = session.exec(q).all()
    return SubCategoriesPublic(data=[SubCategoryPublic.model_validate(s) for s in items], count=len(items))


@router.post("/subcategories", response_model=SubCategoryPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def create_subcategory(*, session: SessionDep, body: SubCategoryCreate) -> Any:
    if not session.get(Category, body.category_id):
        raise HTTPException(status_code=404, detail="Category not found.")
    if session.exec(select(SubCategory).where(SubCategory.name == body.name, SubCategory.category_id == body.category_id)).first():
        raise HTTPException(status_code=409, detail="SubCategory already exists in this category.")
    sub = SubCategory(name=body.name, description=body.description, category_id=body.category_id)
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


@router.patch("/subcategories/{subcategory_id}", response_model=SubCategoryPublic, dependencies=[require_roles(UserRole.HQ_ADMIN)])
def update_subcategory(*, session: SessionDep, subcategory_id: uuid.UUID, body: SubCategoryUpdate) -> Any:
    sub = session.get(SubCategory, subcategory_id)
    if not sub:
        raise HTTPException(status_code=404, detail="SubCategory not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(sub, field, value)
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub
