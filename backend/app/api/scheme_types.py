from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models.scheme_type import SchemeType
from app.models.user import User
from app.schemas.scheme_type import SchemeTypeCreate, SchemeTypeRead, SchemeTypeUpdate

router = APIRouter(prefix="/scheme-types", tags=["scheme-types"])


@router.get("", response_model=list[SchemeTypeRead])
def list_schemes(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[SchemeType]:
    return db.query(SchemeType).order_by(SchemeType.id).all()


@router.post("", response_model=SchemeTypeRead, status_code=status.HTTP_201_CREATED)
def create_scheme(
    body: SchemeTypeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> SchemeType:
    if db.query(SchemeType).filter(SchemeType.business_code == body.business_code).first():
        raise HTTPException(status_code=400, detail="方案业务ID已存在")
    row = SchemeType(
        business_code=body.business_code,
        category=body.category,
        name=body.name,
        remark=body.remark,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{scheme_id}", response_model=SchemeTypeRead)
def get_scheme(
    scheme_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> SchemeType:
    row = db.get(SchemeType, scheme_id)
    if row is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    return row


@router.patch("/{scheme_id}", response_model=SchemeTypeRead)
def update_scheme(
    scheme_id: int,
    body: SchemeTypeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> SchemeType:
    row = db.get(SchemeType, scheme_id)
    if row is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    if body.business_code is not None and body.business_code != row.business_code:
        if db.query(SchemeType).filter(SchemeType.business_code == body.business_code).first():
            raise HTTPException(status_code=400, detail="方案业务ID已存在")
        row.business_code = body.business_code
    if body.category is not None:
        row.category = body.category
    if body.name is not None:
        row.name = body.name
    if body.remark is not None:
        row.remark = body.remark
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{scheme_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scheme(
    scheme_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    row = db.get(SchemeType, scheme_id)
    if row is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    db.delete(row)
    db.commit()
