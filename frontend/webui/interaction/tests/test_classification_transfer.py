"""NiceGUI's actual upload callbacks and local navigation; no database."""

import asyncio
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from nicegui import ui
from nicegui.testing import User
from starlette.datastructures import UploadFile

from frontend.webui.classification_transfer import import_dialog, export_control

pytest_plugins = ["nicegui.testing.user_plugin"]
pytestmark = pytest.mark.asyncio


async def test_import_upload_and_stay_in_list(user: User):
    api = AsyncMock()
    refresh = AsyncMock()

    @ui.page("/transfer")
    def page():
        ui.label("Schemes list")
        ui.button(
            "Import", on_click=lambda: import_dialog(api, lambda: True, refresh, str)
        )

    await user.open("/transfer")
    user.find("Import").click()
    await user.should_see("Import classification scheme")
    uploader = next(iter(user.find(ui.upload).elements))
    uploader.handle_uploads(
        [UploadFile(BytesIO(b'{"sample":true}'), filename="scheme.json")]
    )
    await asyncio.sleep(0.05)
    # Select only the dialog's Import button.
    buttons = sorted(
        [b for b in user.find(ui.button).elements if b.text == "Import"],
        key=lambda b: b.id,
    )
    buttons[-1].mark("confirm")
    user.find(marker="confirm").click()
    await asyncio.sleep(0.05)
    assert api.request.await_count == 1
    assert api.request.call_args.kwargs["params"] == {"format": "json"}
    refresh.assert_awaited_once()
    await user.should_see("Schemes list")


async def test_import_abandonment_does_not_refresh(user: User):
    gate = asyncio.Event()
    live = {"active": True}
    refresh = AsyncMock()

    async def request(*a, **kw):
        await gate.wait()
        return {"id": 5}

    api = AsyncMock()
    api.request.side_effect = request

    @ui.page("/transfer-abandon")
    def page():
        import_dialog(api, lambda: live["active"], refresh, str)

    await user.open("/transfer-abandon")
    next(iter(user.find(ui.upload).elements)).handle_uploads(
        [UploadFile(BytesIO(b"a,b"), filename="scheme.csv")]
    )
    await asyncio.sleep(0.05)
    user.find("Import", kind=ui.button).click()
    await asyncio.sleep(0.05)
    live["active"] = False
    gate.set()
    await asyncio.sleep(0.05)
    refresh.assert_not_awaited()


async def test_word_languages_loaded_only_on_action(user: User):
    api = AsyncMock()
    api.localization_bootstrap.return_value = {
        "effective_language": "en",
        "supported_languages": [
            {"language_tag": "en", "native_name": "English"},
            {"language_tag": "ar", "native_name": "العربية"},
            {"language_tag": "fr", "native_name": "Français"},
        ],
    }

    @ui.page("/transfer-export")
    def page():
        export_control(
            api, {"id": 7, "code": "GCS", "title": "Scheme"}, lambda: True, str
        )

    await user.open("/transfer-export")
    api.localization_bootstrap.assert_not_awaited()
    api.request.assert_not_awaited()
    user.find("Export").click()
    await user.should_see("MS Word")
    items = sorted(user.find(ui.menu_item).elements, key=lambda item: item.id)
    items[-1].mark("word-menu")
    user.find(marker="word-menu").click()
    await user.should_see("Document language")
    language = next(iter(user.find(ui.select).elements))
    assert set(language.options) == {"en", "ar", "fr"}
    api.localization_bootstrap.assert_awaited_once()
    api.request.assert_not_awaited()


async def test_word_dialog_is_not_owned_by_transient_menu(user: User):
    api = AsyncMock()
    api.localization_bootstrap.return_value = {
        "effective_language": "en",
        "supported_languages": [{"language_tag": "en", "native_name": "English"}],
    }
    gate = asyncio.Event()

    async def request(*args, **kwargs):
        await gate.wait()
        return b"document"

    api.request.side_effect = request

    @ui.page("/word-busy")
    def page():
        export_control(
            api, {"id": 1, "code": "S", "title": "Scheme"}, lambda: True, str
        )

    await user.open("/word-busy")
    user.find("Export", kind=ui.button).click()
    sorted(user.find(ui.menu_item).elements, key=lambda item: item.id)[-1].mark("word")
    user.find(marker="word").click()
    await user.should_see("Document language")
    dialog = next(iter(user.find(ui.dialog).elements))
    assert not isinstance(dialog.parent_slot.parent, ui.menu_item)
    user.find("Download", kind=ui.button).click()
    await asyncio.sleep(0.05)
    download = next(
        button for button in user.find(ui.button).elements if button.text == "Download"
    )
    assert download.props["loading"] and not download.enabled
    # The callback itself also protects against a queued second click.
    user.find("Download", kind=ui.button).click()
    await asyncio.sleep(0.05)
    assert api.request.await_count == 1
    gate.set()
    await asyncio.sleep(0.05)
    assert api.request.call_args.kwargs["params"] == {
        "format": "docx",
        "language": "en",
    }


async def test_removed_upload_clears_confirmation(user: User):
    api = AsyncMock()

    @ui.page("/remove-upload")
    def page():
        import_dialog(api, lambda: True, AsyncMock(), str)

    await user.open("/remove-upload")
    uploader = next(iter(user.find(ui.upload).elements))
    uploader.handle_uploads([UploadFile(BytesIO(b"data"), filename="scheme.json")])
    await asyncio.sleep(0.05)
    confirm = next(
        button for button in user.find(ui.button).elements if button.text == "Import"
    )
    assert confirm.enabled
    listener = next(
        listener
        for listener in uploader._event_listeners.values()
        if listener.type == "removed"
    )
    uploader._handle_event({"listener_id": listener.id, "args": []})
    assert not confirm.enabled
