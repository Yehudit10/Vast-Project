#!/usr/bin/env python3
"""
backup.py — PostgreSQL base backup with retention.
Waits until Postgres is ready and out of recovery, then runs pg_basebackup.
"""

import os, subprocess, time
from datetime import datetime

BACKUP_DIR = os.getenv("BACKUP_DIR", "/var/lib/postgresql/backups")
RETENTION = int(os.getenv("RETENTION", "7"))
PGUSER = os.getenv("POSTGRES_USER", "missions_user")
PGPASSWORD = os.getenv("POSTGRES_PASSWORD", "pg123")
PGHOST = os.getenv("PGHOST", "127.0.0.1")
PGPORT = os.getenv("PGPORT", "5432")
PGDATABASE = os.getenv("POSTGRES_DB", "missions_db")
os.environ["PGPASSWORD"] = PGPASSWORD

def wait_for_postgres():
    while True:
        try:
            subprocess.check_call(
                ["pg_isready", "-h", PGHOST, "-p", PGPORT, "-U", PGUSER, "-d", PGDATABASE],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print("[BACKUP] PostgreSQL is ready ✅")
            break
        except subprocess.CalledProcessError:
            print("[BACKUP] Waiting for PostgreSQL...")
            time.sleep(2)

def wait_until_not_in_recovery():
    while True:
        try:
            result = subprocess.check_output([
                "psql", "-h", PGHOST, "-p", PGPORT, "-U", PGUSER, "-d", PGDATABASE,
                "-t", "-c", "SELECT pg_is_in_recovery();"
            ], text=True).strip()
            if result == "f":
                print("[BACKUP] Database is out of recovery ✅")
                break
            else:
                print("[BACKUP] Still in recovery, waiting...")
        except subprocess.CalledProcessError:
            print("[BACKUP] Waiting for PostgreSQL to accept queries...")
        time.sleep(3)

def run_backup():
    wait_for_postgres()
    wait_until_not_in_recovery()

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_name = "base_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    print(f"[BACKUP] Starting base backup → {backup_path}")
    subprocess.check_call([
        "pg_basebackup", "-h", PGHOST, "-p", PGPORT, "-U", PGUSER,
        "-D", backup_path, "-Fp", "-Xs", "-P", "-R", "-v"
    ])

    # Retention
    backups = sorted([b for b in os.listdir(BACKUP_DIR) if b.startswith("base_")], reverse=True)
    for i, b in enumerate(backups):
        if i >= RETENTION:
            subprocess.call(["rm", "-rf", os.path.join(BACKUP_DIR, b)])
            print(f"[BACKUP] Removed old backup {b}")

if __name__ == "__main__":
    run_backup()
