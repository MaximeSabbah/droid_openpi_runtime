#!/usr/bin/env bash
set -euo pipefail

docker compose -f docker-compose.singlepc.yml run --rm openpi-droid bash
