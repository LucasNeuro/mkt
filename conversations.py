from typing import Any

from storage import save_uazapi_messages, save_webhook_message, upsert_group


def extract_messages_list(uazapi_data: Any) -> list[dict]:
    if isinstance(uazapi_data, list):
        return [m for m in uazapi_data if isinstance(m, dict)]
    if not isinstance(uazapi_data, dict):
        return []

    for key in ("messages", "data", "items", "result"):
        value = uazapi_data.get(key)
        if isinstance(value, list):
            return [m for m in value if isinstance(m, dict)]

    if uazapi_data.get("messageid") or uazapi_data.get("id"):
        return [uazapi_data]

    return []


def persist_webhook_payload(payload: dict) -> dict | None:
    return save_webhook_message(payload)


def persist_sync_batch(group_jid: str, group_name: str | None, items: list[dict]) -> int:
    upsert_group(group_jid, group_name)
    return save_uazapi_messages(group_jid, items)
