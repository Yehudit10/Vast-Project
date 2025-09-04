#!/usr/bin/env python3
"""
recover.py — PostgreSQL PITR recovery (enhanced version)
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

def choose_backup_for_time(target_time_str):
    """Pick the latest base backup that is <= target_time"""
    target_time = datetime.fromisoformat(target_time_str)
    candidates = []
    for b in os.listdir(BACKUPS_DIR):
        if b.startswith("base_"):
            try:
                ts = datetime.strptime(b.replace("base_", ""), "%Y%m%d_%H%M%S")
                if ts <= target_time:
                    candidates.append((ts, b))
            except ValueError:
                continue
    if not candidates:
        print(f"[RECOVERY] ERROR: no base backup found before {target_time}")
        sys.exit(1)
    chosen = max(candidates, key=lambda x: x[0])[1]
    print(f"[RECOVERY] Chosen base backup: {chosen}")
    return os.path.join(BACKUPS_DIR, chosen)

def recover(mode, arg=None):
    # Determine backup to use
    if mode == "time":
        backup = choose_backup_for_time(arg)
        recovery_target = arg
    elif mode == "minutes":
        t = datetime.now() - timedelta(minutes=int(arg))
        backup = choose_backup_for_time(t.isoformat())
        recovery_target = t.isoformat()
    else:
        backups = sorted([b for b in os.listdir(BACKUPS_DIR) if b.startswith("base_")])
        if not backups:
            print("[RECOVERY] ERROR: no backups found")
            sys.exit(1)
        backup = os.path.join(BACKUPS_DIR, backups[-1])
        recovery_target = None

    print(f"[RECOVERY] Using backup {backup}")

    # Wipe current data and restore base backup
    run(["rm", "-rf", f"{PGDATA}/*"], check=False)
    run(["cp", "-R", f"{backup}/.", PGDATA])

    # Write recovery config
    conf_file = os.path.join(PGDATA, "postgresql.auto.conf")
    with open(conf_file, "a") as f:
        f.write(f"\nrestore_command = 'cp {WAL_DIR}/%f %p'\n")
        f.write("recovery_target_action = 'promote'\n")
        if recovery_target:
            f.write(f"recovery_target_time = '{recovery_target}'\n")

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
        if len(sys.argv) < 3:
            print("Usage: recover.py time 'YYYY-MM-DD HH:MM:SS+TZ'")
            sys.exit(1)
        recover("time", sys.argv[2])
    elif sys.argv[1] == "minutes":
        if len(sys.argv) < 3:
            print("Usage: recover.py minutes <N>")
            sys.exit(1)
        recover("minutes", sys.argv[2])
