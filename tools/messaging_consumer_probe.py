"""Run the production portable frontend adapter in a separate acceptance process.

Only disposable test databases may launch this helper. Token arrives through the
process environment, never a command line or output. Checkpoints model browser
sessionStorage; output records presentation effects without message content.
"""

import asyncio
import json
import os
from pathlib import Path
import sys

from frontend.webui.api_client import ErmsApiClient
from frontend.webui.messaging_live import LiveMailbox, stream_events


async def main():
    assert "erms_messaging_test_" in os.environ["DATABASE_URL"]
    base, transport, directory = sys.argv[1:]
    folder = Path(directory)
    folder.mkdir(exist_ok=True)
    checkpoint = folder / "cursor"
    token = os.environ["MESSAGING_PROBE_TOKEN"]
    api = ErmsApiClient(base)
    api.set_session_token(token)

    async def load():
        return checkpoint.read_text() if checkpoint.exists() else 0

    async def save(value):
        temporary = folder / "cursor.tmp"
        temporary.write_text(str(value))
        temporary.replace(checkpoint)

    async def present(kind, value):
        if kind == "message":
            value = value["id"]
        with (folder / "events.jsonl").open("a") as output:
            output.write(json.dumps({"kind": kind, "value": value}) + "\n")

    async def events(selected):
        async for value in stream_events(
            base, token, transport if transport != "auto" else selected
        ):
            yield value

    mailbox = LiveMailbox(
        api=api,
        events=events,
        load_cursor=load,
        save_cursor=save,
        present=present,
        active=lambda: True,
    )
    try:
        await mailbox.run()
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
