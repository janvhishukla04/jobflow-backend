from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from pydantic import BaseModel

app = FastAPI()

# Security setup
SECRET_KEY = "your-secret-key-change-this-in-production"  # Change this!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class UserSignup(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

# Database connection function
def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
    else:
        database_url = "postgresql://root:sa123@localhost/jobflow_db"
    
    return psycopg2.connect(database_url)

# Initialize database
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Create jobs table with user_id
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
        print("✅ Database tables ready")
    except Exception as e:
        print(f"❌ Database init error: {e}")

init_db()

# Auth helper functions
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ---------- SIGNUP ----------
@app.post("/signup")
def signup(user: UserSignup):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email=%s OR username=%s", 
                      (user.email, user.username))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="User already exists")
        
        # Create user
        hashed_pw = hash_password(user.password)
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (user.username, user.email, hashed_pw)
        )
        user_id = cursor.fetchone()[0]
        conn.commit()
        
        # Create token
        token = create_access_token({"user_id": user_id})
        
        return {
            "token": token,
            "user": {"id": user_id, "username": user.username, "email": user.email}
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# ---------- LOGIN ----------
@app.post("/login")
def login(user: UserLogin):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("SELECT * FROM users WHERE email=%s", (user.email,))
        db_user = cursor.fetchone()
        
        if not db_user or not verify_password(user.password, db_user['password_hash']):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        token = create_access_token({"user_id": db_user['id']})
        
        return {
            "token": token,
            "user": {
                "id": db_user['id'],
                "username": db_user['username'],
                "email": db_user['email']
            }
        }
    finally:
        cursor.close()
        conn.close()

# ---------- GET JOBS (Protected) ----------
@app.get("/jobs")
def get_jobs(user_id: int = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM jobs WHERE user_id=%s ORDER BY applied_date DESC", (user_id,))
    jobs = cursor.fetchall()
    cursor.close()
    conn.close()
    return jobs

# ---------- ADD JOB (Protected) ----------
@app.post("/jobs")
def add_job(job: dict, user_id: int = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO jobs (company, role, status, applied_date, user_id) VALUES (%s,%s,%s,%s,%s)"
    values = (job["company"], job["role"], job["status"], job["applied_date"], user_id)
    cursor.execute(sql, values)
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Job added"}

# ---------- DELETE JOB (Protected) ----------
@app.delete("/jobs/{job_id}")
def delete_job(job_id: int, user_id: int = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE id=%s AND user_id=%s", (job_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Deleted"}

# ---------- UPDATE JOB (Protected) ----------
@app.put("/jobs/{job_id}")
def update_job(job_id: int, job: dict, user_id: int = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "UPDATE jobs SET company=%s, role=%s, status=%s, applied_date=%s WHERE id=%s AND user_id=%s"
    values = (job["company"], job["role"], job["status"], job["applied_date"], job_id, user_id)
    cursor.execute(sql, values)
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Updated"}
