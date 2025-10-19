#!/usr/bin/env python3
"""
cron_backup.py — Runs backup via cron, logs to BACKUP_DIR/cron.log
"""

import os, subprocess, datetime

BACKUP_DIR = os.getenv("BACKUP_DIR", "/var/lib/postgresql/backups")
LOGFILE = os.path.join(BACKUP_DIR, "cron.log")

with open(LOGFILE, "a") as f:
    f.write(f"[CRON-BACKUP] Starting backup at {datetime.datetime.now()}\n")

try:
    subprocess.check_call(["python3", "/usr/local/bin/backup.py"],
                          stdout=open(LOGFILE, "a"),
                          stderr=open(LOGFILE, "a"))
    with open(LOGFILE, "a") as f:
        f.write(f"[CRON-BACKUP] Finished at {datetime.datetime.now()}\n")
except Exception as e:
    with open(LOGFILE, "a") as f:
        f.write(f"[CRON-BACKUP] ERROR: {e}\n")
