from __future__ import annotations
from datetime import datetime
import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.providers.docker.operators.docker import DockerOperator


PROJECT_ROOT = "/opt/airflow/dags/leaf-counting"
PYTHON_BIN   = "python"
WEIGHTS      = f"{PROJECT_ROOT}/weights/best.pt"


OUT_RUN      = f"{PROJECT_ROOT}/runs_local/airflow_run"
STAGING_DIR  = "/opt/airflow/staging/input"

tz = pendulum.timezone("Asia/Jerusalem")

with DAG(
    dag_id="leaf_pipeline_v2",
    start_date=datetime(2025, 10, 1, tzinfo=tz),
    schedule=None,
    catchup=False,
    default_args={"owner": "leafcounting", "retries": 0},
    tags=["leaf-counting", "detect", "pwb", "crop", "minio"],
) as dag:

   
    RUN_ID_DATE = "{{ dag_run.conf.get('run_id') or logical_date.in_timezone('Asia/Jerusalem').strftime('%Y/%m/%d/%H%M') }}"

    # -----------------------------
    # STAGE INPUT
    # -----------------------------
    stage_input = BashOperator(
        task_id="stage_input",
        bash_command="""
set -euo pipefail
python -m pip install --no-cache-dir -q \
  --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org \
  awscli \
|| apt-get update && apt-get install -y -qq ca-certificates awscli \
|| python -m pip install --no-cache-dir -q \
     --index-url http://pypi.org/simple \
     --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org \
     awscli
STAGING_DIR='{{ params.staging_dir }}'
INPUT_MODE='minio'
mkdir -p "$STAGING_DIR"; rm -rf "$STAGING_DIR"/*
if [ "$INPUT_MODE" = 'minio' ]; then
  SRC_BUCKET='{{ dag_run.conf.get("src_bucket", var.value.leaf_minio_bucket | default("imagery")) }}'
  SRC_PREFIX='leaves/examples'
  ENDPOINT_URL='{{ conn.minio_s3.extra_dejson.endpoint_url | default("http://host.docker.internal:9001") }}'
  export AWS_ACCESS_KEY_ID='{{ conn.minio_s3.login }}'
  export AWS_SECRET_ACCESS_KEY='{{ conn.minio_s3.password }}'
  export AWS_DEFAULT_REGION='{{ conn.minio_s3.extra_dejson.region_name or "us-east-1" }}'
  export AWS_S3_FORCE_PATH_STYLE=true
  export AWS_EC2_METADATA_DISABLED=true
  echo "[stage] source=minio s3://$SRC_BUCKET/$SRC_PREFIX -> $STAGING_DIR (endpoint=$ENDPOINT_URL)"
  python -m awscli s3 sync "s3://$SRC_BUCKET/$SRC_PREFIX" "$STAGING_DIR" --endpoint-url "$ENDPOINT_URL"
else
  INPUT_DIR='{{ params.project_root }}/demo_images'
  echo "[stage] source=local $INPUT_DIR -> $STAGING_DIR"
  rsync -a --delete "$INPUT_DIR"/ "$STAGING_DIR"/
fi
""",
        params={"staging_dir": STAGING_DIR, "project_root": PROJECT_ROOT},
        env={"PYTHONUNBUFFERED": "1"},
    )

    # -----------------------------
    # DETECT  -> imagery/leaves/<YYYY>/<MM>/<DD>/<HHMM>/detect/
    # -----------------------------
    detect = BashOperator(
        task_id="detect",
        bash_command="""
set -euo pipefail

PROJECT_ROOT='{{ params.project_root }}'
PY='{{ params.python_bin }}'; if ! command -v "$PY" >/dev/null 2>&1; then PY='python'; fi

export PYTHONEXECUTABLE="$PY"   

INPUT_DIR='{{ params.staging_dir }}'
OUT_LOCAL_DET='{{ params.out_run }}/detect'
WEIGHTS='{{ params.weights }}'

DATE_ONLY='{{ dag_run.conf.get("run_id") or logical_date.in_timezone("Asia/Jerusalem").strftime("%Y/%m/%d/%H%M") }}'

DEST_PREFIX="leaves/${DATE_ONLY}/detect"

# MinIO:
#   ל-SDK (minio-py) 
ENDPOINT_HOSTPORT='{{ (conn.minio_s3.host or "host.docker.internal") }}:{{ (conn.minio_s3.port or 9001) }}'
#   ל-awscli צריך URL מלא:
ENDPOINT_URL='{{ conn.minio_s3.extra_dejson.endpoint_url | default("http://host.docker.internal:9001") }}'
BUCKET='{{ var.value.leaf_minio_bucket | default("imagery") }}'
export AWS_ACCESS_KEY_ID='{{ conn.minio_s3.login }}'
export AWS_SECRET_ACCESS_KEY='{{ conn.minio_s3.password }}'
export AWS_DEFAULT_REGION='us-east-1'
export AWS_S3_FORCE_PATH_STYLE=true

mkdir -p "$OUT_LOCAL_DET"

cd "$PROJECT_ROOT"
$PY src/detect_only.py \
    --input "$INPUT_DIR" \
    --out   "$OUT_LOCAL_DET" \
    --weights "$WEIGHTS" \
    --conf 0.25 --imgsz 896 --device cpu \
    --minio-endpoint "$ENDPOINT_HOSTPORT" \
    --minio-access   "$AWS_ACCESS_KEY_ID" \
    --minio-secret   "$AWS_SECRET_ACCESS_KEY" \
    --minio-bucket   "$BUCKET" \
    --minio-prefix   "leaves/${DATE_ONLY}" \
    --run-id         "detect"

# יישור קו לנתיב המדויק:
pip install -q awscli || true
python -m awscli s3 sync "$OUT_LOCAL_DET"/ "s3://$BUCKET/$DEST_PREFIX/" --endpoint-url "$ENDPOINT_URL"
python -m awscli s3 ls "s3://$BUCKET/$DEST_PREFIX/" --recursive --endpoint-url "$ENDPOINT_URL" || true
""",
        params={
            "project_root": PROJECT_ROOT,
            # "python_bin": PYTHON_BIN,
            "python_bin": "/usr/local/bin/python",
            "staging_dir": STAGING_DIR,
            "out_run": OUT_RUN,
            "weights": WEIGHTS,
            "run_id_date": RUN_ID_DATE,
        },
        env={"PYTHONUNBUFFERED": "1"},
    )

    # -----------------------------
    # PREDICT_PWB -> imagery/leaves/<YYYY>/<MM>/<DD>/<HHMM>/pwb/
    # -----------------------------
    pwb = BashOperator(
        task_id="predict_pwb",
        bash_command="""
set -euo pipefail

PROJECT_ROOT='{{ params.project_root }}'
PY='{{ params.python_bin }}'; if ! command -v "$PY" >/dev/null 2>&1; then PY='python'; fi
INPUT_DIR='{{ params.staging_dir }}'
OUT_LOCAL_PWB='{{ params.out_run }}/pwb'
WEIGHTS='{{ params.weights }}'

DATE_ONLY='{{ dag_run.conf.get("run_id") or logical_date.in_timezone("Asia/Jerusalem").strftime("%Y/%m/%d/%H%M") }}'

DEST_PREFIX="leaves/${DATE_ONLY}/pwb"

ENDPOINT_HOSTPORT='{{ (conn.minio_s3.host or "host.docker.internal") }}:{{ (conn.minio_s3.port or 9001) }}'
ENDPOINT_URL='{{ conn.minio_s3.extra_dejson.endpoint_url | default("http://host.docker.internal:9001") }}'
BUCKET='{{ var.value.leaf_minio_bucket | default("imagery") }}'
export AWS_ACCESS_KEY_ID='{{ conn.minio_s3.login }}'
export AWS_SECRET_ACCESS_KEY='{{ conn.minio_s3.password }}'
export AWS_DEFAULT_REGION='us-east-1'
export AWS_S3_FORCE_PATH_STYLE=true

mkdir -p "$OUT_LOCAL_PWB"

cd "$PROJECT_ROOT"
$PY src/predict_pyramid_wbf.py \
    --input "$INPUT_DIR" \
    --out   "$OUT_LOCAL_PWB" \
    --weights "$WEIGHTS" \
    --scales 0.75,1.0,1.25 --conf 0.25 --iou 0.55 --imgsz 896 --device cpu \
    --minio-endpoint "$ENDPOINT_HOSTPORT" \
    --minio-access   "$AWS_ACCESS_KEY_ID" \
    --minio-secret   "$AWS_SECRET_ACCESS_KEY" \
    --minio-bucket   "$BUCKET" \
    --minio-prefix   "leaves/${DATE_ONLY}" \
    --run-id         "pwb"

pip install -q awscli || true
python -m awscli s3 sync "$OUT_LOCAL_PWB"/ "s3://$BUCKET/$DEST_PREFIX/" --endpoint-url "$ENDPOINT_URL"
python -m awscli s3 ls "s3://$BUCKET/$DEST_PREFIX/" --recursive --endpoint-url "$ENDPOINT_URL" || true
""",
        params={
            "project_root": PROJECT_ROOT,
            # "python_bin": PYTHON_BIN,
           "python_bin": "/usr/local/bin/python", 

            "staging_dir": STAGING_DIR,
            "out_run": OUT_RUN,
            "weights": WEIGHTS,
            "run_id_date": RUN_ID_DATE,
        },
        env={"PYTHONUNBUFFERED": "1"},
    )

   
    crop = BashOperator(
    task_id="crop",
    bash_command="""
    set -euo pipefail

    PROJECT_ROOT='{{ params.project_root }}'
    PY='{{ params.python_bin }}'; if ! command -v "$PY" >/dev/null 2>&1; then PY='python'; fi
    OUT_LOCAL_CROP='{{ params.out_run }}/crop'
    PWB_LOCAL='{{ params.out_run }}/pwb'
    RUN_ID_DATE='{{ dag_run.conf.get("run_id") or logical_date.in_timezone("Asia/Jerusalem").strftime("%Y/%m/%d/%H%M") }}'

    RUN_ID_CROP="${RUN_ID_DATE}/crop"

    ENDPOINT_URL='{{ conn.minio_s3.extra_dejson.endpoint_url | default("http://host.docker.internal:9001") }}'
    BUCKET='{{ var.value.leaf_minio_bucket | default("imagery") }}'
    export AWS_ACCESS_KEY_ID='{{ conn.minio_s3.login }}'
    export AWS_SECRET_ACCESS_KEY='{{ conn.minio_s3.password }}'
    export AWS_DEFAULT_REGION='us-east-1'
    export AWS_S3_FORCE_PATH_STYLE=true

   
    export DEVICE_ID="${DEVICE_ID:-dev1}"

    mkdir -p "$OUT_LOCAL_CROP"

    # 1)crop 
    if [ -f "$PROJECT_ROOT/src/crop_only.py" ]; then
      cd "$PROJECT_ROOT"
      $PY src/crop_only.py --input "$PWB_LOCAL" --out "$OUT_LOCAL_CROP"
    elif [ -f "$PROJECT_ROOT/src/crop_from_meta.py" ]; then
      cd "$PROJECT_ROOT"
      $PY src/crop_from_meta.py --input "$PWB_LOCAL" --out "$OUT_LOCAL_CROP"
    else
      echo "[crop] No crop script found; will only sync if $OUT_LOCAL_CROP has files."
    fi

    # 2) (: <device>_<YYYYMMDD>T<HHMMSS>Z[ _suffix].ext)
    
    python -m pip install -q pillow piexif || true
    export OUT_LOCAL_CROP 
    python - <<'PY'
import os, re, sys, time
from datetime import datetime, timezone
OUT = os.environ.get("OUT_LOCAL_CROP", "")
DEVICE = os.environ.get("DEVICE_ID", "dev1")

if not OUT or not os.path.isdir(OUT):
    sys.exit(0)

IMG_EXT = {".jpg",".jpeg",".png",".webp",".tif",".tiff",".bmp"}
iso_re = re.compile(r"^[A-Za-z0-9\-]+_\d{8}T\d{6}Z(?:[ _][^/\\\\]+)?\\.[A-Za-z0-9]+$")

def get_ts_from_exif(path):
    try:
        import piexif
        from PIL import Image
        with Image.open(path) as im:
            exif = im.info.get("exif")
            if not exif:
                return None
        exif_dict = piexif.load(exif)
        dt = exif_dict["Exif"].get(piexif.ExifIFD.DateTimeOriginal) or \
             exif_dict["Exif"].get(piexif.ExifIFD.DateTimeDigitized) or \
             exif_dict["0th"].get(piexif.ImageIFD.DateTime)
        if not dt:
            return None
        # EXIF: "YYYY:MM:DD HH:MM:SS"
        s = dt.decode() if isinstance(dt, bytes) else dt
        dt_obj = datetime.strptime(s, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt_obj
    except Exception:
        return None

def ts_for_file(path):
    dt = get_ts_from_exif(path)
    if dt is None:
        # fallback: mtime כ-UTC
        mt = os.path.getmtime(path)
        dt = datetime.fromtimestamp(mt, tz=timezone.utc)
    return dt

renamed = 0
skipped = 0
for root, _, files in os.walk(OUT):
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext not in IMG_EXT:
            continue
        if iso_re.match(f):
            skipped += 1
            continue
        old = os.path.join(root, f)
        dt = ts_for_file(old)
        ts = dt.strftime("%Y%m%dT%H%M%SZ")
        # suffix 
        base = os.path.splitext(f)[0]
        suffix = ""
        if base and base.lower() not in {"img","image","photo","dsc","dscn"}:
            
            cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-_.")
            if cleaned and cleaned != ts:
                suffix = f"_{cleaned}"
        new_name = f"{DEVICE}_{ts}{suffix}{ext}"
        new = os.path.join(root, new_name)
        if new == old:
            skipped += 1
            continue
        
        i = 1
        new_final = new
        while os.path.exists(new_final):
            new_final = os.path.join(root, f"{os.path.splitext(new_name)[0]}_{i}{ext}")
            i += 1
        os.rename(old, new_final)
        print(f"[crop][rename] {f} -> {os.path.basename(new_final)}")
        renamed += 1

print(f"[crop][rename] done: renamed={renamed}, already_ok={skipped}")
PY

    # 3)MinIO
    pip install -q awscli || true
    if [ -d "$OUT_LOCAL_CROP" ] && [ "$(ls -A "$OUT_LOCAL_CROP" || true)" ]; then
      python -m awscli s3 sync "$OUT_LOCAL_CROP"/ "s3://$BUCKET/leaves/$RUN_ID_CROP/" --endpoint-url "$ENDPOINT_URL"
    else
      echo "[crop] WARNING: no local crops found to upload."
    fi

    python -m awscli s3 ls "s3://$BUCKET/leaves/$RUN_ID_CROP/" --recursive --endpoint-url "$ENDPOINT_URL" || true
    """,
    params={
        "project_root": PROJECT_ROOT,
        "python_bin": PYTHON_BIN,
        "out_run": OUT_RUN,
        "run_id_date": RUN_ID_DATE,
    },
    env={"PYTHONUNBUFFERED": "1"},
)


    detection_jobs = DockerOperator(
    task_id="detection_jobs",
    image="detection-jobs:cpu-lts",
    docker_url="unix://var/run/docker.sock",
    api_version="auto",
    auto_remove=True,
    mount_tmp_dir=False,
    working_dir="/app",
    network_mode="ag_cloud",
    environment={
        "MINIO_ENDPOINT": "{{ conn.minio_s3.extra_dejson.endpoint_url | default('http://minio-hot:9001') }}",
        "AWS_ACCESS_KEY_ID": "{{ conn.minio_s3.login }}",
        "AWS_SECRET_ACCESS_KEY": "{{ conn.minio_s3.password }}",
        "AWS_S3_FORCE_PATH_STYLE": "true",
        "AWS_DEFAULT_REGION": "us-east-1",
        "DATABASE_URL": "postgresql+psycopg2://missions_user:pg123@postgres:5432/missions_db",
        "USER": "root",
        "HOME": "/root",
    },
    command=[
        "/bin/bash","-lc", r'''
set -euo pipefail
echo "[DJ] START"; whoami; pwd; python3 -V
python3 -m pip install --no-cache-dir -q awscli || true

RID='{{ dag_run.conf.get("run_id") or logical_date.in_timezone("Asia/Jerusalem").strftime("%Y/%m/%d/%H%M") }}'
BUCKET='{{ var.value.leaf_minio_bucket | default("imagery") }}'
SRC="s3://${BUCKET}/leaves/${RID}/crop/"
ENDPOINT="${MINIO_ENDPOINT:-http://minio-hot:9001}"

mkdir -p /work/in /work/out
echo "[DJ] sync from ${SRC} via ${ENDPOINT}"
python3 -m awscli s3 cp --recursive "$SRC" /work/in --endpoint-url "$ENDPOINT" || true

IN_DIR="/work/in"
READY_DIR="/work/in_ready"
DEVICE_ID="${DEVICE_ID:-dev1}"
rm -rf "$READY_DIR" && mkdir -p "$READY_DIR"

while IFS= read -r -d '' f; do
  base="$(basename "$f")"
  stem="$(printf '%s\n' "$base" | sed -n 's/^\([A-Za-z0-9-]\+_[0-9]\{8\}T[0-9]\{6\}Z\).*/\1/p')"
  [ -n "$stem" ] || { echo "[DJ][skip] no stem in $base"; continue; }
  outdir="$READY_DIR/$stem"
  mkdir -p "$outdir"
  cp -p "$f" "$outdir/$base"
done < <(find "$IN_DIR" -type f -print0)

echo "[DJ][ready] tree under: $READY_DIR"

FLAT_DIR="/work/in_flat"
rm -rf "$FLAT_DIR" && mkdir -p "$FLAT_DIR"
find "$READY_DIR" -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' -o -iname '*.tif' -o -iname '*.tiff' -o -iname '*.bmp' \) -print0 \
| while IFS= read -r -d '' f; do
  base="$(basename "$f")"
  
  out="$FLAT_DIR/$base"; i=1
  while [ -e "$out" ]; do
    ext="${base##*.}"; stem="${base%.*}"
    out="$FLAT_DIR/${stem}_$i.$ext"; i=$((i+1))
  done
  cp -p "$f" "$out"
done

echo "[DJ][flat] files in $FLAT_DIR:"
ls -1 "$FLAT_DIR" | sed -n '1,50p'
export INPUT_DIR_FOR_RUNNER="$FLAT_DIR"
# === DB bootstrap: ensure required table exists ===
python3 - <<'PY'
import os
from sqlalchemy import create_engine, text


ddl = """
CREATE TABLE IF NOT EXISTS public.leaf_disease_types (
    id   SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS public.leaf_reports (
    id BIGSERIAL PRIMARY KEY,
    device_id TEXT NOT NULL,
    leaf_disease_type_id INTEGER NOT NULL REFERENCES public.leaf_disease_types(id) ON DELETE RESTRICT,
    ts TIMESTAMPTZ NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    sick BOOLEAN NOT NULL
);


CREATE INDEX IF NOT EXISTS ix_leaf_reports_ts ON public.leaf_reports (ts);
CREATE INDEX IF NOT EXISTS ix_leaf_reports_type ON public.leaf_reports (leaf_disease_type_id);
CREATE INDEX IF NOT EXISTS ix_leaf_reports_device_ts ON public.leaf_reports (device_id, ts);
"""

url = os.environ["DATABASE_URL"]
eng = create_engine(url, future=True)
with eng.begin() as conn:
    conn.execute(text(ddl))
print("[DJ][db] ensured table public.leaf_disease_types")
PY


export PYTHONPATH=/app
python3 - <<'PY'
import os, sys, importlib
os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL",""))
inp = os.environ.get('INPUT_DIR_FOR_RUNNER','/work/in_flat')
print("[DJ] runner input dir:", inp)

try:
    files = [f for f in os.listdir(inp) if os.path.isfile(os.path.join(inp,f))]
    print(f"[DJ] flat file count: {len(files)}")
    for f in files[:10]:
        print("[DJ] sample:", f)
except Exception as e:
    print("[DJ] listdir failed:", e)

mod = importlib.import_module('agri_baseline.src.batch_runner')
sys.argv = ['batch_runner.py', '--input', inp, '--mission','1']
exit_code = 0
try:
    mod.main()
except SystemExit as e:
    exit_code = int(e.code) if isinstance(e.code, int) else 1
sys.exit(exit_code)
PY

echo "[DJ] DONE"
        '''
    ],
)


    disease_monitor = DockerOperator(
    task_id="disease_monitor",
    image="disease-monitor:cpu-lts",
    entrypoint=["/bin/sh","-c"],
    command=[r'''
set -eu
echo "[DM] START"; whoami; pwd; python3 -V || true

echo "[DM][env] DATABASE_URL=$DATABASE_URL"
echo "[DM][env] Dropping PG* env if present (to avoid overrides)"
unset PGHOST PGPORT PGDATABASE PGPASSWORD PGUSER 2>/dev/null || true

# ---- DDL via DATABASE_URL only ----
python3 - <<'PY'
import os, sys, time
import psycopg2

DDL = """
CREATE TABLE IF NOT EXISTS alerts_leaves (
  id bigserial PRIMARY KEY,
  entity_id text NOT NULL,
  rule text NOT NULL,
  window_start timestamptz NOT NULL,
  window_end   timestamptz NOT NULL,
  score double precision NOT NULL,
  first_seen timestamptz NOT NULL,
  last_seen  timestamptz NOT NULL,
  status text NOT NULL CHECK (status IN ('OPEN','ACK','RESOLVED')),
  meta_json jsonb
);
CREATE INDEX IF NOT EXISTS ix_alerts_leaves_entity_rule ON alerts_leaves(entity_id, rule);
CREATE INDEX IF NOT EXISTS ix_alerts_leaves_status ON alerts_leaves(status);
"""

dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
print("[DM][db] Using DSN:", dsn.replace(os.environ.get("DATABASE_URL",""), "***redacted***"))

for i in range(12):
    try:
        with psycopg2.connect(dsn, connect_timeout=4) as conn:
            with conn.cursor() as cur:
                cur.execute(DDL)
        print("[DM][db] DDL applied OK.")
        break
    except Exception as e:
        print(f"[DM][db] retry {i+1}/12: {e}")
        time.sleep(5)
else:
    sys.exit("[DM][db] DDL failed after retries")
PY

exec python -m disease_monitor.cli --config /app/configs/config.docker.yaml --log-level INFO

'''],
    environment={
        "DATABASE_URL": "postgresql://missions_user:pg123@postgres:5432/missions_db",
    },
    working_dir="/app",
    docker_url="unix://var/run/docker.sock",
    api_version="auto",
    auto_remove=True,
    network_mode="ag_cloud",
    dag=dag,
)



    stage_input >> detect >> pwb >> crop >> detection_jobs>>disease_monitor
