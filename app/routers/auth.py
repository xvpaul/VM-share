#VM_share/app/routers/auth.py
import logging
import os
import configs.log_config as logs
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from methods.database.database import get_db
from methods.database.models import User

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
    print(f'Error: {e}')
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
                logging.info(f"VM_share/app/routers/auth.py: User '{login}' logged in successfully (via /register)")
                return {
                    "message": "Logged in",
                    "id": existing.id,
                    "access_token": token,
                    "token_type": "bearer"
                }
            else:
                logging.warning(f"VM_share/app/routers/auth.py: Login failed for existing user '{login}': wrong password")
                raise HTTPException(status_code=401, detail="User exists, wrong password")

        hashed = Authentification.hash_password(password)
        new_u = User(login=login, hashed_password=hashed)
        db.add(new_u)
        db.commit()
        db.refresh(new_u)

        token = Authentification.create_access_token({"sub": new_u.login})
        logging.info(f"VM_share/app/routers/auth.py: New user '{login}' registered successfully")
        return {
            "message": "User registered",
            "id": new_u.id,
            "access_token": token,
            "token_type": "bearer"
        }

    except Exception as e:
        logging.exception(f"VM_share/app/routers/auth.py: Registration/login error for user '{body.get('login', 'unknown')}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/token")
def login_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    from methods.auth.auth import Authentification
    try:
        auth = Authentification(form_data.username, form_data.password)
        user = auth.authenticate_user(db)
        if not user:
            logging.warning(f"VM_share/app/routers/auth.py: Token login failed: Invalid credentials for '{form_data.username}'")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = auth.create_access_token({"sub": user.login})
        logging.info(f"VM_share/app/routers/auth.py: User '{user.login}' authenticated via /token")
        return {"access_token": token, "token_type": "bearer"}

    except Exception as e:
        logging.exception(f"VM_share/app/routers/auth.py: Login error for user '{form_data.username}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
