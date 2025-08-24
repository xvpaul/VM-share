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
from configs.config import COOKIE_MAX_AGE
from methods.manager.SessionManager import get_session_store, SessionStore
from utils import cleanup_vm


logger = logging.getLogger(__name__)

class LoginJSON(BaseModel):
    username: str
    password: str


router = APIRouter()

@router.post("/register")
async def register_user(request: Request, db: Session = Depends(get_db)):
    from methods.auth.auth import Authentification
    try:
        body = await request.json()
        login = body.get("login")   # <------ swap to username back
        password = body.get("password")

        if not login or not password:
            logger.warning("VM_share/app/routers/auth.py: Registration failed: missing login or password")
            raise HTTPException(status_code=400, detail="Missing login or password")
        
        existing = db.query(User).filter(User.login == login).first()
        if existing:
            if Authentification.verify_password(password, existing.hashed_password):
                # token = Authentification.create_access_token({"sub": existing.login})
                # resp = JSONResponse({
                #     "message": "Logged in",
                #     "id": existing.id,
                #     "access_token": token,
                #     "token_type": "bearer"
                # })
                # resp.set_cookie(
                #     key="access_token",
                #     value=token,
                #     httponly=True,
                #     secure=False,      # <------ TRUE!!!!
                #     samesite="lax",
                #     path="/",
                #     max_age=60*60*8,  
                # )
                # return resp
                raise HTTPException(status_code=409, detail="User exists")
            else:
                logger.warning(f"VM_share/app/routers/auth.py: Login failed for existing user '{login}': wrong password")
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
        # resp.set_cookie(
        #     key="access_token",
        #     value=token,
        #     httponly=True,
        #     secure=False,
        #     samesite="lax", # <----- switch to lax back
        #     path="/",
        #     max_age=60*60*8,
        # )
        dev_localhost = os.getenv("DEV", "true").lower() in ("1", "true", "yes")
        set_auth_cookie(resp, token, dev_localhost=dev_localhost)

        return resp
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"VM_share/app/routers/auth.py: Registration/login error for user '{body.get('login', 'unknown')}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.post("/login")
async def login_user(payload: LoginJSON, db: Session = Depends(get_db)):
    try:
        logger.info(f"VM_share/app/routers/auth.py: /login attempt for user '{payload.username}'")

        auth = Authentification(payload.username, payload.password)
        user = auth.authenticate_user(db)
        if not user:
            logger.warning(f"VM_share/app/routers/auth.py: /login failed for '{payload.username}' (invalid creds)")
            raise HTTPException(status_code=401, detail="Invalid username or password")

        token = auth.create_access_token({"sub": user.login})
        logger.info(f"VM_share/app/routers/auth.py: /login issued JWT for user '{user.login}' (id={user.id})")

        resp = JSONResponse({
            "message": "Login successful",
            "id": user.id,
            "access_token": token,
            "token_type": "bearer"
        })

        dev_localhost = os.getenv("DEV", "true").lower() in ("1", "true", "yes")
        logger.info(
            "VM_share/app/routers/auth.py: Setting auth cookie for user '%s' "
            "(dev_localhost=%s => secure=%s, samesite='lax', max_age=%s)",
            user.login, dev_localhost, str(not dev_localhost).lower(), COOKIE_MAX_AGE
        )

        set_auth_cookie(resp, token, dev_localhost=dev_localhost)
        logger.info(f"VM_share/app/routers/auth.py: /login succeeded for '{user.login}' (cookie set)")
        return resp

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"VM_share/app/routers/auth.py: Exception during /login for user '{payload.username}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def set_auth_cookie(resp: JSONResponse, token: str, *, dev_localhost: bool = True):
    logger.info(
        f"VM_share/app/routers/auth.py: Setting auth cookie "
        f"(secure={not dev_localhost}, samesite='lax', max_age={COOKIE_MAX_AGE})"
    )
    resp.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=not dev_localhost,   # <----- SET TRUE!!!
        samesite="lax",             # <----- NONE
        path="/",
        max_age=COOKIE_MAX_AGE,
    )

@router.post("/token")
def login_token_alias(payload: LoginJSON, db: Session = Depends(get_db)):
    from methods.auth.auth import Authentification
    try:
        logger.info(f"VM_share/app/routers/auth.py: /token login attempt for user '{payload.username}'")

        auth = Authentification(payload.username, payload.password)
        user = auth.authenticate_user(db)
        if not user:
            logger.warning(f"VM_share/app/routers/auth.py: /token login failed for '{payload.username}' (invalid creds)")
            raise HTTPException(status_code=401, detail="Invalid username or password")

        token = auth.create_access_token({"sub": user.login})
        logger.info(f"VM_share/app/routers/auth.py: /token issued JWT for user '{user.login}' (id={user.id})")

        resp = JSONResponse({"access_token": token, "token_type": "bearer", "id": user.id})

        dev_localhost = os.getenv("DEV", "true").lower() in ("1", "true", "yes")
        logger.info(
            "VM_share/app/routers/auth.py: Setting auth cookie for user '%s' "
            "(dev_localhost=%s => secure=%s, samesite='lax', max_age=%s)",
            user.login, dev_localhost, str(not dev_localhost).lower(), COOKIE_MAX_AGE
        )

        set_auth_cookie(resp, token, dev_localhost=dev_localhost)  # FALSE FALSE FALSE!!!
        logger.info(f"VM_share/app/routers/auth.py: /token login succeeded for '{user.login}' (cookie set)")
        return resp

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"VM_share/app/routers/auth.py: Exception during /token for user '{payload.username}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/logout")
def logout_user(
    user = Depends(get_current_user),
    store = Depends(get_session_store),
):
    logger.info("logger out user %s: deleting auth cookie and terminating sessions...", getattr(user, "id", "?"))

    resp = JSONResponse({"message": "Logged out"})
    try:
        resp.delete_cookie("access_token", path="/")
    except Exception:
        logger.exception("Failed to delete access_token cookie for user %s", getattr(user, "id", "?"))

    vmid = None
    try:
        sess = store.get_running_by_user(user.id) 
        if isinstance(sess, dict):
            vmid = sess.get("vmid")
    except Exception:
        logger.exception("get_running_by_user failed for user %s", user.id)

    if vmid:
        logger.info("Terminating VM %s for user %s ...", vmid, user.id)
        try:
            cleanup_vm(vmid, store)
        except Exception:
            logger.exception("cleanup_vm failed for vmid=%s (user=%s)", vmid, user.id)
        try:
            store.delete(vmid)
        except Exception:
            logger.exception("store.delete failed for vmid=%s", vmid)
    else:
        logger.info("Logout: no active VM for user %s (nothing to terminate).", user.id)

    return resp

@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    logger.info(f"VM_share/app/routers/auth.py: /me endpoint called by user '{user.login}' (id={user.id})")
    return {"id": user.id, "login": user.login, "role": user.role}


# @router.post("/token-json")
# def login_token_json(payload: LoginJSON, db: Session = Depends(get_db)):
#     from methods.auth.auth import Authentification
#     try:
#         auth = Authentification(payload.username, payload.password)
#         user = auth.authenticate_user(db)
#         if not user:
#             raise HTTPException(status_code=401, detail="Invalid credentials")
#         token = auth.create_access_token({"sub": user.login})
#         return {"access_token": token, "token_type": "bearer"}
#     except Exception as e:
#         logger.exception("Login error: %s", e)
#         raise HTTPException(status_code=500, detail="Internal server error")

# @router.get("/me")
# async def me(user: User = Depends(get_current_user)):
#     return {"id": user.id, "login": user.login}