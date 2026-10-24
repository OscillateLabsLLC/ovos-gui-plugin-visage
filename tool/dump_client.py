#!/usr/bin/env python3
"""Connect to a GUI-1 endpoint, send hello, print every server frame as one JSON line.

    python tool/dump_client.py ws://127.0.0.1:18182/gui1 --session default
"""
import argparse
import json
import sys

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", nargs="?", default="ws://127.0.0.1:18182/gui1")
    parser.add_argument("--session", default="default")
    parser.add_argument("--protocol", default="ovos-gui-1")
    parser.add_argument("--version", type=int, default=1)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    hello = {"type": "hello", "protocol": args.protocol, "version": args.version,
             "session_id": args.session, "client": "dump_client/0.1.0"}
    with connect(args.url) as conn:
        conn.send(json.dumps(hello))
        try:
            while True:
                print(conn.recv(), flush=True)
        except KeyboardInterrupt:
            return 0
        except ConnectionClosed as closed:
            frame = closed.rcvd
    code, reason = (frame.code, frame.reason) if frame else (None, "no close frame")
    print(json.dumps({"_closed": code, "reason": reason}), file=sys.stderr)
    return 0 if code in (1000, 1001) else 1


if __name__ == "__main__":
    sys.exit(main())
