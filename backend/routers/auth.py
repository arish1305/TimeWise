from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import database, models, schemas, auth

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

@router.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=user.role,
        full_name=user.full_name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if user and auth.verify_password(form_data.password, user.hashed_password):
        access_token = auth.create_access_token(
            data={
                "sub": user.username,
                "role": models.UserRole.ADMIN,
            }
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "role": models.UserRole.ADMIN,
            "username": user.username,
            "full_name": user.full_name,
            "faculty_id": None,
        }

    faculty = db.query(models.Faculty).filter(models.Faculty.faculty_id_code == form_data.username).first()
    if faculty and faculty.faculty_id_code and form_data.password == faculty.faculty_id_code:
        access_token = auth.create_access_token(
            data={
                "sub": faculty.faculty_id_code,
                "role": models.UserRole.FACULTY,
                "faculty_id": faculty.id,
            }
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "role": models.UserRole.FACULTY,
            "username": faculty.faculty_id_code,
            "full_name": faculty.name,
            "faculty_id": faculty.id,
        }

    raise credentials_exception
