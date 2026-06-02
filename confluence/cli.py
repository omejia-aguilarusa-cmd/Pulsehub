from __future__ import annotations

import argparse
import asyncio

import uvicorn

from confluence.logging import setup_logging
from confluence.scheduler.jobs import start_scheduler, run_scan
from confluence.db.session import init_db


def main() -> None:
    parser = argparse.ArgumentParser(prog="confluence")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("server", help="Run FastAPI server")

    p_scan = sub.add_parser("scan", help="Run a one-off scan")
    p_scan.add_argument("mode", choices=["day", "swing", "hold"], help="Scan mode")

    sub.add_parser("schedule", help="Run APScheduler for periodic scans")

    args = parser.parse_args()
    setup_logging()
    if args.cmd == "server":
        asyncio.run(init_db())
        uvicorn.run("confluence.server.app:app", host="0.0.0.0", port=8000, reload=False)
    elif args.cmd == "scan":
        asyncio.run(init_db())
        asyncio.run(run_scan(args.mode))
    elif args.cmd == "schedule":
        # Keep the loop alive
        asyncio.run(init_db())
        start_scheduler()
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
