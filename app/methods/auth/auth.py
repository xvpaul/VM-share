# /app/methods/auth/auth.py
import logging
import os
import configs.log_config as logs
from sqlalchemy.orm import Session 
from fastapi import Request, HTTPException
from passlib.context import CryptContext
# from fastapi.security import OAuth2PasswordBearer
from methods.database.database import SessionLocal
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from methods.database.models import User
from configs.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Authentification:
    def __init__(self, login: str, password: str) -> None:
        self.login = login
        self.password = password

    def authenticate_user(self, db: Session):
        """Compares input login with stored login (case-sensitive)"""
        user = db.query(User).filter(User.login == self.login).first()
        if not user:
            logging.warning(f"VM_share/app/methods/auth/auth.py: Authentication failed: user '{self.login}' not found")
            return None
        if not self.verify_password(self.password, user.hashed_password):
            logging.warning(f"VM_share/app/methods/auth/auth.py: Authentication failed: invalid password for user '{self.login}'")
            return None
        logging.info(f"VM_share/app/methods/auth/auth.py: User '{self.login}' successfully authenticated")
        return user
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        return pwd_context.verify(password, hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        logging.debug("VM_share/app/methods/auth/auth.py: Hashing a password")
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(data: dict, expires_delta=None) -> str:
        """Creates a JWT token"""
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode = data.copy()
        to_encode.update({"exp": expire})
        token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        logging.info(f"VM_share/app/methods/auth/auth.py: Access token created for user '{data.get('sub', 'unknown')}'")
        return token

    @staticmethod
    def decode_access_token(token: str) -> dict:
        """Decodes JWT and returns the payload (raises error if invalid)"""
        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            logging.info(f"VM_share/app/methods/auth/auth.py: Access token decoded for user '{decoded.get('sub', 'unknown')}'")
            return decoded
        except JWTError:
            logging.warning("VM_share/app/methods/auth/auth.py: Failed to decode access token: invalid or expired token")
            raise ValueError("Invalid or expired token")


async def get_current_user(request: Request) -> User:
    token = request.cookies.get("access_token")  # cookie first
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):]
    if not token:
        logging.warning("Authorization failed: no token in header or cookie")
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        login = payload.get("sub")
        if not login:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.login == login).first()
        finally:
            db.close()

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        logging.info(f"VM_share/app/methods/auth/auth.py: Authenticated request from user '{login}'")
        return user

    except JWTError as e:
        logging.warning(f"VM_share/app/methods/auth/auth.py: Token decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except Exception as e:
        logging.exception(f"VM_share/app/methods/auth/auth.py: Unexpected error during token validation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
