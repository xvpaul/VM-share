from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from methods.database.database import get_db
from methods.database.models import User

router = APIRouter()

@router.post("/register")
async def register_user(request: Request, db: Session = Depends(get_db)):
    from methods.auth.auth import Authentification
    body = await request.json()
    login    = body.get("login")
    password = body.get("password")

    if not login or not password:
        raise HTTPException(status_code=400, detail="Missing login or password")

    existing = db.query(User).filter(User.login == login).first()
    if existing:
        if Authentification.verify_password(password, existing.hashed_password):
            token = Authentification.create_access_token({"sub": existing.login})
            return {
                "message": "Logged in",
                "id": existing.id,
                "access_token": token,
                "token_type": "bearer"
            }
        else:
            raise HTTPException(status_code=401, detail="User exists, wrong password")

    hashed = Authentification.hash_password(password)
    new_u  = User(login=login, hashed_password=hashed)
    db.add(new_u)
    db.commit()
    db.refresh(new_u)

    token = Authentification.create_access_token({"sub": new_u.login})
    return {
        "message": "User registered",
        "id": new_u.id,
        "access_token": token,
        "token_type": "bearer"
    }

@router.post("/token")
def login_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    from methods.auth.auth import Authentification
    auth = Authentification(form_data.username, form_data.password)
    user = auth.authenticate_user(db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth.create_access_token({"sub": user.login})
    return {"access_token": token, "token_type": "bearer"}
