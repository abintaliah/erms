import asyncio
from collections import deque
import pytest
from frontend.webui.messaging_live import LiveMailbox


def run(coro):
    return asyncio.run(coro)


class FakeApi:
    def __init__(self, pages):
        self.pages = deque(pages)
        self.calls = []

    async def request(self, method, path, **kwargs):
        self.calls.append((path, kwargs))
        if path.endswith("unread-count"):
            return {"unread_count": 7}
        return self.pages.popleft()


def page(cursor, *ids, more=False):
    return {
        "items": [
            {"id": identity, "mailbox_sequence": cursor - len(ids) + i + 1}
            for i, identity in enumerate(ids)
        ],
        "next_cursor": cursor,
        "has_more": more,
    }


def adapter(api, events=None, initial=0):
    output, checkpoints = [], []
    active = {"value": True}

    async def load():
        return initial

    async def save(cursor):
        checkpoints.append(cursor)

    async def present(kind, value):
        output.append((kind, value))

    live = LiveMailbox(
        api=api,
        events=events,
        load_cursor=load,
        save_cursor=save,
        present=present,
        active=lambda: active["value"],
    )
    return live, output, checkpoints, active


def test_reconciliation_pages_one_summary_safe_cursor_and_no_content_cache():
    async def scenario():
        api = FakeApi([page(2, "a", "b", more=True), page(5, "e"), page(5)])
        live, output, saved, _ = adapter(api)
        await live.reconcile(summary=True)
        assert output == [("summary", 3), ("unread", 7), ("refresh", None)]
        assert saved == [2, 5]
        await live.reconcile(summary=True)
        assert [x for x in output if x[0] == "summary"] == [("summary", 3)]
        assert api.calls[1][1]["params"] == {"after": 2, "limit": 50}

    run(scenario())


def test_duplicate_out_of_order_hints_and_unknown_versions_reconcile():
    async def scenario():
        api = FakeApi([page(2, "a", "b"), page(4, "c", "d"), page(4)])

        async def events(transport):
            yield {"schema_version": 1, "event_type": "reconciliation_required"}
            yield {
                "schema_version": 1,
                "event_type": "message_available",
                "mailbox_cursor": 4,
            }
            yield {
                "schema_version": 1,
                "event_type": "message_available",
                "mailbox_cursor": 3,
            }
            yield {
                "schema_version": 1,
                "event_type": "message_available",
                "mailbox_cursor": 4,
            }
            yield {"schema_version": 2, "event_type": "future_event"}
            active["value"] = False

        live, output, saved, active = adapter(api, events)
        await live.run()
        assert [v["id"] for k, v in output if k == "message"] == ["c", "d"]
        assert [v for k, v in output if k == "summary"] == [2]
        assert saved == [2, 4, 4]

    run(scenario())


def test_identity_abandonment_discards_pending_response():
    async def scenario():
        api = FakeApi([page(1, "private")])
        live, output, saved, active = adapter(api)
        original = api.request

        async def abandoned(*args, **kwargs):
            result = await original(*args, **kwargs)
            active["value"] = False
            return result

        api.request = abandoned
        await live.reconcile(summary=False)
        assert not output and not saved

    run(scenario())


def test_storage_failure_does_not_repeat_live_toast_in_same_page():
    async def scenario():
        api = FakeApi([page(1, "a"), page(1)])
        live, output, _, _ = adapter(api)

        async def unavailable(cursor):
            raise OSError("browser storage unavailable")

        live.save_cursor = unavailable
        with pytest.raises(OSError):
            await live.reconcile(summary=False)
        assert live.cursor == 1
        with pytest.raises(OSError):
            await live.reconcile(summary=False)
        assert [v["id"] for k, v in output if k == "message"] == ["a"]

    run(scenario())


def test_websocket_failure_uses_sse_and_recovers_gap_once():
    async def scenario():
        api = FakeApi([page(2, "a", "b"), page(2), page(3, "c")])
        transports = []

        async def events(transport):
            transports.append(transport)
            if transport == "ws":
                raise OSError("gateway interrupted")
            yield {"schema_version": 1, "event_type": "reconciliation_required"}
            yield {
                "schema_version": 1,
                "event_type": "message_available",
                "mailbox_cursor": 3,
            }
            active["value"] = False

        live, output, saved, active = adapter(api, events)
        await live.run()
        assert transports == ["ws", "sse"]
        assert [x for x in output if x[0] == "summary"] == [("summary", 2)]
        assert [v["id"] for k, v in output if k == "message"] == ["c"]

    run(scenario())


def test_persisted_cursor_survives_frontend_restart_and_is_identity_scoped():
    async def scenario():
        api = FakeApi([page(20)])

        async def events(transport):
            yield {"schema_version": 1, "event_type": "reconciliation_required"}
            active["value"] = False

        live, output, saved, active = adapter(api, events, initial=20)
        await live.run()
        assert api.calls[0][1]["params"]["after"] == 20
        assert not [x for x in output if x[0] == "summary"]

    run(scenario())


def test_reconnect_summary_marks_test_notifications():
    async def scenario():
        response=page(2,'normal','test')
        response['items'][1]['is_test']=True
        api=FakeApi([response])
        live,output,_,_=adapter(api)
        await live.reconcile(summary=True)
        assert ('summary',{'count':2,'test_count':1}) in output
    run(scenario())


def test_checkpoint_survives_new_login_and_isolates_api_and_user():
    from frontend.webui.messaging_live import mailbox_cursor_key
    async def scenario():
        storage = {}
        key = mailbox_cursor_key('http://api.example', 7)
        assert key == mailbox_cursor_key('http://api.example/', 7)
        assert key != mailbox_cursor_key('http://another-api.example', 7)
        assert key != mailbox_cursor_key('http://api.example', 8)
        outputs = []
        # Separate adapters represent separate authenticated logins; both use
        # the same account checkpoint, despite having different session tokens.
        for pages in ([page(1,'old')], [page(1)], [page(2,'new')]):
            live, output, _, active = adapter(FakeApi(pages))
            async def load(): return storage.get(key, 0)
            async def save(value): storage[key] = value
            async def events(transport):
                yield {'schema_version':1,'event_type':'reconciliation_required'}
                active['value'] = False
            live.load_cursor, live.save_cursor, live.events = load, save, events
            await live.run()
            outputs.append(output)
        assert [v for k,v in outputs[0] if k=='summary']==[1]
        assert not [v for k,v in outputs[1] if k in ('summary','message')]
        assert [v for k,v in outputs[2] if k=='summary']==[1]
        assert storage[key]==2
    run(scenario())
