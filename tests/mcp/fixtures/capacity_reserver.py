"""Independent SQLite reservation contender for capacity acceptance."""

import sys
import time
from pathlib import Path

from ai_code_quality.mcp.contracts import ServiceError, encode
from ai_code_quality.mcp.store import Store


def main():
    root, coordination, identity = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    store = Store(root, "process-race", capacity=27 * 1024 * 1024)
    (coordination / (identity + ".ready")).write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + 15
    while not (coordination / "go").exists():
        if time.monotonic() > deadline:
            raise TimeoutError("Capacity race was not released")
        time.sleep(0.01)
    try:
        with store.transaction() as db:
            store.reserve(db, identity)
        outcome = "accepted"
    except ServiceError as exc:
        outcome = exc.code
    print(encode({"identity": identity, "outcome": outcome}), flush=True)


if __name__ == "__main__":
    main()
