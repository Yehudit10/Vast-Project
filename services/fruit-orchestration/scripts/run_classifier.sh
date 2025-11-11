#!/usr/bin/env bash
set -euo pipefail

# נעביר משתנים דרך env מה־BashOperator
HOST_DATA_DIR="${HOST_DATA_DIR:-/data}"
IMAGES_DIR="${IMAGES_DIR:-/data/images}"
RUN_ID="${RUN_ID:-manual}"

echo "[run_classifier] start | RUN_ID=${RUN_ID} | IMAGES_DIR=${IMAGES_DIR}"

# הדגמה: כאן מריצים את הפרויקט שלך (python, poetry, וכו')
# לדוגמה:
# python -m fruit_classifier.batch --images "${IMAGES_DIR}" --run-id "${RUN_ID}"

# כרגע רק נכתוב פלט לדוגמה ללוגים:
echo "[run_classifier] processing images under ${IMAGES_DIR} ..."
sleep 1
echo "[run_classifier] done."

exit 0
