from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="sa123",
    database="jobflow_db"
)

# ---------- GET JOBS ----------
@app.get("/jobs")
def get_jobs():
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM jobs")
    return cursor.fetchall()

# ---------- ADD JOB ----------
@app.post("/jobs")
def add_job(job: dict):
    cursor = db.cursor()
    sql = "INSERT INTO jobs (company, role, status, applied_date) VALUES (%s,%s,%s,%s)"
    values = (job["company"], job["role"], job["status"], job["applied_date"])
    cursor.execute(sql, values)
    db.commit()
    return {"message": "Job added"}

# ---------- DELETE JOB ----------
@app.delete("/jobs/{job_id}")
def delete_job(job_id: int):
    cursor = db.cursor()
    cursor.execute("DELETE FROM jobs WHERE id=%s", (job_id,))
    db.commit()
    return {"message": "Deleted"}

# ---------- UPDATE JOB ----------
@app.put("/jobs/{job_id}")
def update_job(job_id: int, job: dict):
    cursor = db.cursor()
    sql = "UPDATE jobs SET company=%s, role=%s, status=%s, applied_date=%s WHERE id=%s"
    values = (job["company"], job["role"], job["status"], job["applied_date"], job_id)
    cursor.execute(sql, values)
    db.commit()
    return {"message": "Updated"}