# auth.py
from sqlalchemy.orm import Session 
from fastapi import Request, HTTPException
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from methods.database.database import SessionLocal
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from methods.database.models import User

SECRET_KEY = "your-secret-key"  # keep this secret!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Authentification:
    def __init__(self, login: str, password: str) -> None:
        self.login = login
        self.password = password

    def authenticate_user(self, db: Session):
        """Compares input login with stored login (case-sensitive)"""
        user = db.query(User).filter(User.login == self.login).first()
        if not user:
            return None
        if not self.verify_password(self.password, user.hashed_password):
            return None 
        return user
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        return pwd_context.verify(password, hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(data: dict, expires_delta=None) -> str:
        """Creates a JWT token"""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def decode_access_token(token: str) -> dict:
        """Decodes JWT and returns the payload (raises error if invalid)"""
        try:
            return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            raise ValueError("Invalid or expired token")


async def get_current_user(request: Request) -> User:
    print("🔐 [get_current_user] Authorization header:", request.headers.get("Authorization"))
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = auth_header[len("Bearer "):]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        login = payload.get("sub")
        if not login:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        db = SessionLocal()
        user = db.query(User).filter(User.login == login).first()
        db.close()

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return user

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")