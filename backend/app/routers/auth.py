import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserLogin, UserOut, Token
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user

logger = logging.getLogger("jam_analyzer")

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists"
        )
    
    # Hash password and save user
    hashed_pw = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        hashed_password=hashed_pw,
        name=user_data.name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=Token)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    logger.info(f"[Auth Login] Incoming login request for email: {login_data.email}")
    logger.info(f"[Auth Login] Request payload: email={login_data.email}, password_len={len(login_data.password)}")
    
    logger.info(f"[Auth Login] Performing database lookup for user: {login_data.email}")
    user = db.query(User).filter(User.email == login_data.email).first()
    
    if not user:
        logger.warning(f"[Auth Login] Database lookup failed: user {login_data.email} not found.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    logger.info(f"[Auth Login] User found. Verifying password...")
    if not verify_password(login_data.password, user.hashed_password):
        logger.warning(f"[Auth Login] Password verification failed for user: {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create JWT Access Token
    access_token = create_access_token(data={"sub": user.id})
    logger.info(f"[Auth Login] Authentication successful. Access token generated for user id: {user.id}")
    logger.info("User Logged In")
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
