#!/usr/bin/env python3
"""Run Wathefni durable email-ingress jobs outside the webhook process."""

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid

import app
import durable_email_ingress


def main() -> None:
    app.assert_runtime_environment_binding()
    parser = argparse.ArgumentParser(description="Process durable Postmark intake jobs.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument(
        "--job-type",
        action="append",
        choices=sorted(durable_email_ingress.JOB_TYPES),
        help="Restrict this worker to one or more job types.",
    )
    parser.add_argument("--sweep-orphans", action="store_true")
    parser.add_argument("--apply-orphan-sweep", action="store_true")
    args = parser.parse_args()
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:10]}"

    while True:
        result = app.run_durable_email_ingress_worker(
            limit=max(1, args.limit),
            worker_id=worker_id,
            job_types=args.job_type,
        )
        if args.sweep_orphans:
            result["orphan_storage"] = durable_email_ingress.orphan_storage_report(
                db_connect=app.db_connect,
                config=app.durable_email_ingress_config(),
                delete=bool(args.apply_orphan_sweep),
            )
        print(json.dumps(app.json_safe(result), ensure_ascii=False), flush=True)
        if not args.loop:
            return
        if not result.get("processed"):
            time.sleep(max(0.25, args.sleep))


if __name__ == "__main__":
    main()
