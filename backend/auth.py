from datetime import datetime, timedelta
from typing import Optional
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from pydantic import BaseModel
from models import User, Faculty, UserRole

# Secret key for JWT (in production, use env var)
import os
from dotenv import load_dotenv
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Make auto_error=False to allow optional token for dev bypass
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


class AuthenticatedUser(BaseModel):
    username: str
    role: str
    full_name: Optional[str] = None
    user_id: Optional[int] = None
    faculty_id: Optional[int] = None

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        faculty_id = payload.get("faculty_id")
        if not username or not role:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    if role == UserRole.ADMIN:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise credentials_exception
        return AuthenticatedUser(
            username=user.username,
            role=UserRole.ADMIN,
            full_name=user.full_name,
            user_id=user.id,
        )

    if role == UserRole.FACULTY:
        faculty = None
        if faculty_id is not None:
            faculty = db.query(Faculty).filter(Faculty.id == faculty_id).first()
        if not faculty:
            faculty = db.query(Faculty).filter(Faculty.faculty_id_code == username).first()
        if not faculty:
            raise credentials_exception
        return AuthenticatedUser(
            username=faculty.faculty_id_code or username,
            role=UserRole.FACULTY,
            full_name=faculty.name,
            faculty_id=faculty.id,
        )

    raise credentials_exception


async def require_admin(current_user: AuthenticatedUser = Depends(get_current_user)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def require_faculty(current_user: AuthenticatedUser = Depends(get_current_user)):
    if current_user.role != UserRole.FACULTY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Faculty access required")
    return current_user
