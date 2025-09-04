#!/usr/bin/env python3
"""
cron_backup.py — Runs backup via cron, logs to /var/lib/postgresql/backups/cron.log
"""

import subprocess, datetime

LOGFILE = "/var/lib/postgresql/backups/cron.log"

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
