"""meowmap backend commands: serve, decide."""

import argparse
import logging
from pathlib import Path

from meowmap_backend.config import from_env
from meowmap_backend.db import connect
from meowmap_backend.ordering import create_approval_requests
from meowmap_backend.subscriber import serve


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meowmap-backend")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="subscribe to MQTT and store events")
    decide = sub.add_parser("decide", help="run the approval rule once against SQLite")
    decide.add_argument("--sqlite", type=Path, default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = from_env()
    if args.cmd == "serve":
        serve(cfg)
        return 0

    path = args.sqlite if args.sqlite is not None else cfg.sqlite_path
    conn = connect(path)
    rows = create_approval_requests(conn)
    print(f"approval_requests_created={len(rows)}")
    for row in rows:
        print(row["message_body"])
        print(f"payment_status={row['payment_status']}")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
