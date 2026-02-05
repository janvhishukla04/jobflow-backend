from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection function
def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Render provides postgres:// but psycopg2 needs postgresql://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
    else:
        # Fallback for local development
        database_url = "postgresql://root:sa123@localhost/jobflow_db"
    
    return psycopg2.connect(database_url)

# Initialize database - create table if it doesn't exist
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id SERIAL PRIMARY KEY,
                company VARCHAR(100),
                role VARCHAR(100),
                status VARCHAR(50),
                applied_date DATE
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database table ready")
    except Exception as e:
        print(f"❌ Database init error: {e}")

# Call init_db when app starts
init_db()

# ---------- GET JOBS ----------
@app.get("/jobs")
def get_jobs():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM jobs")
    jobs = cursor.fetchall()
    cursor.close()
    conn.close()
    return jobs

# ---------- ADD JOB ----------
@app.post("/jobs")
def add_job(job: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO jobs (company, role, status, applied_date) VALUES (%s,%s,%s,%s)"
    values = (job["company"], job["role"], job["status"], job["applied_date"])
    cursor.execute(sql, values)
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Job added"}

# ---------- DELETE JOB ----------
@app.delete("/jobs/{job_id}")
def delete_job(job_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs WHERE id=%s", (job_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Deleted"}

# ---------- UPDATE JOB ----------
@app.put("/jobs/{job_id}")
def update_job(job_id: int, job: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = "UPDATE jobs SET company=%s, role=%s, status=%s, applied_date=%s WHERE id=%s"
    values = (job["company"], job["role"], job["status"], job["applied_date"], job_id)
    cursor.execute(sql, values)
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Updated"}
