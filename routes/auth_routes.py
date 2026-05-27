from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request
)
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

from sqlalchemy.orm import Session

from database import get_db
from models import User, Log
from schemas import UserCreate, UserLogin

from auth import (
    SECRET_KEY,
    ALGORITHM,
    hash_password,
    verify_password,
    create_access_token
)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login",
    auto_error=False
)

# ---------------- SIGNUP ----------------

@router.post("/signup")
def signup(user: UserCreate, request: Request, db: Session = Depends(get_db)):

    existing_user = db.query(User).filter(
        (User.email == user.email) |
        (User.username == user.username)
    ).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    db.add(Log(
        user_id=new_user.id,
        action="signup",
        ip_address=request.client.host
    ))
    db.commit()

    return {"message": "Signup successful"}

# ---------------- LOGIN ----------------

@router.post("/login")
def login(user: UserLogin, request: Request, db: Session = Depends(get_db)):

    existing_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if not existing_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(user.password, existing_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "user_id": existing_user.id,
        "email": existing_user.email
    })

    db.add(Log(
        user_id=existing_user.id,
        action="login",
        ip_address=request.client.host
    ))
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer"
    }

# ---------------- AUTH ----------------

def get_current_user(token: str = Depends(oauth2_scheme)):

    if not token:
        return None
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials"
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("user_id")
        email = payload.get("email")

        if user_id is None:
            raise credentials_exception

        return {
            "user_id": user_id,
            "email": email
        }

    except JWTError:
        raise credentials_exception
    
# ---------------- OPTIONAL AUTH ----------------

def get_optional_user(
    token: str = Depends(oauth2_scheme)
):

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        return {
            "user_id": payload.get("user_id"),
            "email": payload.get("email")
        }

    except:
        return None