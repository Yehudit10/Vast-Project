#!/usr/bin/env bash
set -euo pipefail
cron
tail -F /var/log/cron.log