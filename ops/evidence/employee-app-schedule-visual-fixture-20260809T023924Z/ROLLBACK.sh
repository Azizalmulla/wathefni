#!/usr/bin/env bash
set -euo pipefail
cd /opt/wathefni/orchestrator
.venv/bin/python ops-seed-schedule-visual-fixture.py --cleanup
