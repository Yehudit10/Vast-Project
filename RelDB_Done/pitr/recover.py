#!/usr/bin/env python3
"""
recover.py — PostgreSQL PITR recovery (stable version)
This script prepares the recovery but does NOT start postgres.
You must restart the container afterwards with: docker restart db
"""

import os, sys, subprocess
from datetime import datetime, timedelta

PGDATA = "/var/lib/postgresql/data"
BACKUPS_DIR = "/var/lib/postgresql/backups"
WAL_DIR = "/var/lib/postgresql/wal_archive"

def run(cmd, check=True):
    print(f"[RECOVERY] $ {' '.join(cmd)}")
    return subprocess.run(cmd, shell=False, check=check)

def recover(mode, arg=None):
    # Pick latest backup
    backups = sorted([b for b in os.listdir(BACKUPS_DIR) if b.startswith("base_")])
    if not backups:
        print("[RECOVERY] ERROR: no backups found")
        sys.exit(1)
    backup = os.path.join(BACKUPS_DIR, backups[-1])
    print(f"[RECOVERY] Using backup {backup}")

    # Wipe current data and restore base backup
    run(["rm", "-rf", f"{PGDATA}/*"], check=False)
    run(["cp", "-R", f"{backup}/.", PGDATA])

    # Write recovery config
    conf_file = os.path.join(PGDATA, "postgresql.auto.conf")
    with open(conf_file, "a") as f:
        f.write(f"\nrestore_command = 'cp {WAL_DIR}/%f %p'\n")
        f.write("recovery_target_action = 'promote'\n")
        if mode == "time":
            f.write(f"recovery_target_time = '{arg}'\n")
        elif mode == "minutes":
            t = datetime.now() - timedelta(minutes=int(arg))
            f.write(f"recovery_target_time = '{t.isoformat()}'\n")

    # Create recovery.signal
    open(os.path.join(PGDATA, "recovery.signal"), "w").close()

    print("\n[RECOVERY] Recovery setup complete ✅")
    print("[RECOVERY] Please restart the container to apply recovery:")
    print("           docker restart db\n")
    print("[RECOVERY] After restart, run a manual backup:")
    print("           docker exec -u postgres -it db python3 /usr/local/bin/backup.py\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: recover.py latest|time|minutes [value]")
        sys.exit(1)
    if sys.argv[1] == "latest":
        recover("latest")
    elif sys.argv[1] == "time":
        recover("time", sys.argv[2])
    elif sys.argv[1] == "minutes":
        recover("minutes", sys.argv[2])
