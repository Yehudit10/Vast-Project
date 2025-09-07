#!/usr/bin/env python3
"""
recover.py — PostgreSQL PITR recovery (Safe Mode)
Always prepares recovery without crashing, even if WAL or backups are missing.
Does NOT start Postgres automatically — restart container manually.

Usage:
    recover.py latest
    recover.py minutes <N>
    recover.py time "YYYY-MM-DDTHH:MM:SS+03:00"
"""

import os, sys, subprocess
from datetime import datetime, timedelta

# ==== ENV variables (provided by docker-compose) ====
PGDATA = os.getenv("PGDATA", "/var/lib/postgresql/data")
BACKUPS_DIR = os.getenv("BACKUP_DIR", "/var/lib/postgresql/backups")
WAL_DIR = os.getenv("WAL_DIR", "/var/lib/postgresql/wal_archive")

def run(cmd, check=True):
    """Run a shell command and print it."""
    print(f"[RECOVERY] $ {' '.join(cmd)}")
    return subprocess.run(cmd, shell=False, check=check)

def parse_backup_ts(name):
    """Extract datetime from backup folder name base_YYYYMMDD_HHMMSS"""
    try:
        return datetime.strptime(name.replace("base_", ""), "%Y%m%d_%H%M%S")
    except ValueError:
        return None

def choose_backup_for_time(target_time):
    """
    Choose the latest base backup that is <= target_time.
    If none exist, fallback to the latest available.
    """
    candidates = []
    for b in os.listdir(BACKUPS_DIR):
        if b.startswith("base_"):
            ts = parse_backup_ts(b)
            if ts and ts <= target_time:
                candidates.append((ts, b))
    if not candidates:
        print(f"[RECOVERY] WARNING: No backup found before {target_time}, using latest available.")
        backups = sorted([b for b in os.listdir(BACKUPS_DIR) if b.startswith("base_")])
        if not backups:
            return None
        return os.path.join(BACKUPS_DIR, backups[-1])
    chosen = max(candidates, key=lambda x: x[0])[1]
    print(f"[RECOVERY] Chosen base backup: {chosen}")
    return os.path.join(BACKUPS_DIR, chosen)

def write_recovery_conf(recovery_target=None):
    """
    Write recovery parameters into postgresql.auto.conf
    Adds recovery.signal file to trigger PITR mode.
    """
    conf_file = os.path.join(PGDATA, "postgresql.auto.conf")
    with open(conf_file, "a") as f:
        # Allow recovery to continue even if a WAL file is missing
        f.write(f"\nrestore_command = 'cp {WAL_DIR}/%f %p || true'\n")
        f.write("recovery_target_action = 'promote'\n")
        if recovery_target:
            f.write(f"recovery_target_time = '{recovery_target}'\n")
    # Create recovery.signal
    open(os.path.join(PGDATA, "recovery.signal"), "w").close()

def recover(mode, arg=None):
    """
    Main recovery logic:
      - Pick correct backup depending on mode (latest, minutes, time).
      - Restore base backup into PGDATA.
      - Configure recovery.
      - Print warnings if WAL is incomplete.
    """
    # 1. Pick backup
    if mode == "time":
        try:
            target_time = datetime.fromisoformat(arg)
        except Exception:
            print("[RECOVERY] ERROR: Invalid time format. Use YYYY-MM-DDTHH:MM:SS+TZ")
            sys.exit(1)
        backup = choose_backup_for_time(target_time)
        recovery_target = arg
    elif mode == "minutes":
        t = datetime.now() - timedelta(minutes=int(arg))
        backup = choose_backup_for_time(t)
        recovery_target = t.isoformat()
    else:  # latest
        backups = sorted([b for b in os.listdir(BACKUPS_DIR) if b.startswith("base_")])
        if not backups:
            print("[RECOVERY] WARNING: No backups at all! DB may start empty.")
            backup = None
        else:
            backup = os.path.join(BACKUPS_DIR, backups[-1])
        recovery_target = None

    # 2. Restore base backup
    if backup:
        print(f"[RECOVERY] Using backup {backup}")
        run(["rm", "-rf", f"{PGDATA}/*"], check=False)
        run(["cp", "-R", f"{backup}/.", PGDATA])
    else:
        print("[RECOVERY] No backup restored (DB will try to start with existing PGDATA)")

    # 3. Write recovery config
    write_recovery_conf(recovery_target)

    # 4. Validate WAL presence
    wals = [f for f in os.listdir(WAL_DIR) if f.endswith(".history") or f.isalnum()]
    if not wals:
        print("[RECOVERY] WARNING: No WAL files found in archive — recovery may promote immediately.")

    # 5. Finish
    print("\n[RECOVERY] ✅ Recovery setup complete (Safe Mode)")
    print("Restart the container:")
    print("   docker restart db\n")
    print("Check recovery status:")
    print("   docker exec -it db psql -U missions_user -d missions_db -c \"SELECT pg_is_in_recovery();\"")
    print("When finished, run manual backup:")
    print("   docker exec -u postgres -it db python3 /usr/local/bin/backup.py\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: recover.py latest|time|minutes [value]")
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "latest":
        recover("latest")
    elif mode == "time":
        if len(sys.argv) < 3:
            print("Usage: recover.py time 'YYYY-MM-DDTHH:MM:SS+TZ'")
            sys.exit(1)
        recover("time", sys.argv[2])
    elif mode == "minutes":
        if len(sys.argv) < 3:
            print("Usage: recover.py minutes <N>")
            sys.exit(1)
        recover("minutes", sys.argv[2])
    else:
        print("Usage: recover.py latest|time|minutes [value]")
        sys.exit(1)
