from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import hashlib
from jose import JWTError, jwt
from datetime import datetime, timedelta
from pydantic import BaseModel

# =========================
# APP INIT
# =========================
app = FastAPI()

# =========================
# CORS (FIXED & CORRECT)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://jobflow-frontend-omega.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# SECURITY
# =========================
SECRET_KEY = "jobflow-secret-key-2026-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080
security = HTTPBearer()

# =========================
# MODELS
# =========================
class UserSignup(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class Job(BaseModel):
    company: str
    role: str
    status: str
    applied_date: str

# =========================
# DATABASE
# =========================
def get_db_connection():
    database_url = os.getenv("DATABASE_URL")

    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if not database_url:
        database_url = "postgresql://root:sa123@localhost/jobflow_db"

    return psycopg2.connect(database_url)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            company VARCHAR(100),
            role VARCHAR(100),
            status VARCHAR(50),
            applied_date DATE,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()

init_db()

# =========================
# AUTH HELPERS
# =========================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed

def create_access_token(data: dict):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# =========================
# ROUTES
# =========================
@app.get("/")
def root():
    return {"status": "JobFlow API running"}

# -------- AUTH --------
@app.post("/signup")
def signup(user: UserSignup):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM users WHERE email=%s OR username=%s",
        (user.email, user.username)
    )
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="User already exists")

    hashed = hash_password(user.password)

    cursor.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (%s,%s,%s) RETURNING id",
        (user.username, user.email, hashed)
    )

    user_id = cursor.fetchone()[0]
    conn.commit()

    cursor.close()
    conn.close()

    token = create_access_token({"user_id": user_id})

    return {
        "token": token,
        "user": {
            "id": user_id,
            "username": user.username,
            "email": user.email
        }
    }

@app.post("/login")
def login(user: UserLogin):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("SELECT * FROM users WHERE email=%s", (user.email,))
    db_user = cursor.fetchone()

    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    cursor.close()
    conn.close()

    token = create_access_token({"user_id": db_user["id"]})

    return {
        "token": token,
        "user": {
            "id": db_user["id"],
            "username": db_user["username"],
            "email": db_user["email"]
        }
    }

# -------- JOBS --------
@app.get("/jobs")
def get_jobs(user_id: int = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        "SELECT * FROM jobs WHERE user_id=%s ORDER BY applied_date DESC",
        (user_id,)
    )

    jobs = cursor.fetchall()
    cursor.close()
    conn.close()
    return jobs

@app.post("/jobs")
def add_job(job: Job, user_id: int = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO jobs (company, role, status, applied_date, user_id)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (job.company, job.role, job.status, job.applied_date, user_id)
    )

    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Job added"}

@app.put("/jobs/{job_id}")
def update_job(job_id: int, job: Job, user_id: int = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE jobs
        SET company=%s, role=%s, status=%s, applied_date=%s
        WHERE id=%s AND user_id=%s
        """,
        (job.company, job.role, job.status, job.applied_date, job_id, user_id)
    )

    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Updated"}

@app.delete("/jobs/{job_id}")
def delete_job(job_id: int, user_id: int = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM jobs WHERE id=%s AND user_id=%s",
        (job_id, user_id)
    )

    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Deleted"}
