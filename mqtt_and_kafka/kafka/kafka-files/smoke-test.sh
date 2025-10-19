#!/usr/bin/env bash
set -euo pipefail

# Use the in-container bootstrap; from host use localhost:29092
BOOTSTRAP="${BOOTSTRAP:-localhost:9092}"
TOPIC="dev-robot-telemetry-raw"

# Do NOT create the topic here. It must already exist (created by create-topics.sh)

MSG="hello-from-kcat-$(date +%H:%M:%S)"
echo "[smoke] producing: $MSG"

# Prepare a temporary file to capture the consumer output
TMP="$(mktemp -p /tmp smoke.XXXXXX)"

# Start a one-shot consumer from the END (so it waits for the next produced message)
# Run in background and capture exactly 1 message
kcat -C -b "$BOOTSTRAP" -t "$TOPIC" -o end -e -q -c 1 > "$TMP" &
CID=$!

# Small delay to ensure the consumer is ready to receive
sleep 0.5

# Produce a single message (no key delimiter)
printf "%s\n" "$MSG" | kcat -P -b "$BOOTSTRAP" -t "$TOPIC"

# Wait for the consumer to finish with a soft timeout loop (up to ~10s)
for i in {1..20}; do
  if ! kill -0 "$CID" 2>/dev/null; then break; fi
  sleep 0.5
done
# In case still alive, let it end (won't block if already exited)
wait "$CID" 2>/dev/null || true

echo "[smoke] consuming..."
OUT="$(cat "$TMP" || true)"
rm -f "$TMP"
echo "[smoke] got: $OUT"

if [[ "$OUT" == "$MSG" ]]; then
  echo "[smoke] ✅ PASS"
else
  echo "[smoke] ❌ FAIL" >&2
  exit 2
fi
