# /app/routers/auth.py
import logging
import os
import configs.log_config as logs
from fastapi import APIRouter, Request, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from methods.database.database import get_db
from methods.database.models import User
from pydantic import BaseModel
from methods.auth.auth import get_current_user, Authentification

class LoginJSON(BaseModel):
    username: str
    password: str

"""
Logging configuration 
"""

log_file_path = os.path.join(logs.LOG_DIR, logs.LOG_NAME)

try:
    os.makedirs(logs.LOG_DIR, exist_ok=True)
    logging.basicConfig(
        filename=log_file_path,
        level=logging.INFO,
        format='%(asctime)s.%(msecs)05d %(message)s',
        datefmt='%Y-%m-%d %H-%M-%S',
    )

except Exception as e:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s.%(msecs)05d %(message)s',
        datefmt='%Y-%m-%d %H-%M-%S',
    )
    logging.error(f"Failed to initialize file logging: {e}")



router = APIRouter()

@router.post("/register")
async def register_user(request: Request, db: Session = Depends(get_db)):
    from methods.auth.auth import Authentification
    try:
        body = await request.json()
        login = body.get("login")
        password = body.get("password")

        if not login or not password:
            logging.warning("VM_share/app/routers/auth.py: Registration failed: missing login or password")
            raise HTTPException(status_code=400, detail="Missing login or password")
        
        existing = db.query(User).filter(User.login == login).first()
        if existing:
            if Authentification.verify_password(password, existing.hashed_password):
                token = Authentification.create_access_token({"sub": existing.login})
                resp = JSONResponse({
                    "message": "Logged in",
                    "id": existing.id,
                    "access_token": token,
                    "token_type": "bearer"
                })
                resp.set_cookie(
                    key="access_token",
                    value=token,
                    httponly=True,
                    secure=False,      # set False only for local http testing
                    samesite="lax",
                    path="/",
                    max_age=60*60*8,  
                )
                return resp
            else:
                logging.warning(f"VM_share/app/routers/auth.py: Login failed for existing user '{login}': wrong password")
                raise HTTPException(status_code=401, detail="User exists, wrong password")

        # new user
        hashed = Authentification.hash_password(password)
        new_u = User(login=login, hashed_password=hashed)
        db.add(new_u); db.commit(); db.refresh(new_u)

        token = Authentification.create_access_token({"sub": new_u.login})
        resp = JSONResponse({
            "message": "User registered",
            "id": new_u.id,
            "access_token": token,
            "token_type": "bearer"
        })
        resp.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
            max_age=60*60*8,
        )
        return resp

    except Exception as e:
        logging.exception(f"VM_share/app/routers/auth.py: Registration/login error for user '{body.get('login', 'unknown')}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.post("/login")
async def login_user(payload: LoginJSON, db: Session = Depends(get_db)):
    try:
        auth = Authentification(payload.username, payload.password)
        user = auth.authenticate_user(db)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        token = auth.create_access_token({"sub": user.login})

        resp = JSONResponse({
            "message": "Login successful",
            "id": user.id,
            "access_token": token,
            "token_type": "bearer"
        })
        resp.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=False,   # True in prod (HTTPS)
            samesite="lax",
            path="/"
        )
        return resp

    except Exception as e:
        logging.exception(f"VM_share/app/routers/auth.py: Exception during login for user '{payload.username}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/token")
def login_token_alias(payload: LoginJSON, db: Session = Depends(get_db)):
    from methods.auth.auth import Authentification
    try:
        auth = Authentification(payload.username, payload.password)
        user = auth.authenticate_user(db)
        if not user:
            logging.warning(f"VM_share/app/routers/auth.py: Login failed for user '{payload.username}' via /token")
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = auth.create_access_token({"sub": user.login})
        logging.info(f"VM_share/app/routers/auth.py: User '{user.login}' logged in via /token")
        return {"access_token": token, "token_type": "bearer"}
    except Exception as e:
        logging.exception("Login error via /token: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/logout")
async def logout_user(response: Response):
    # remove cookie so the session ends
    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie("access_token", path="/")
    return response

@router.post("/token-json")
def login_token_json(payload: LoginJSON, db: Session = Depends(get_db)):
    from methods.auth.auth import Authentification
    try:
        auth = Authentification(payload.username, payload.password)
        user = auth.authenticate_user(db)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = auth.create_access_token({"sub": user.login})
        return {"access_token": token, "token_type": "bearer"}
    except Exception as e:
        logging.exception("Login error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "login": user.login}