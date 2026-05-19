import os
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client, create_client

INSTANCE_NAME = os.getenv("UAZAPI_INSTANCE_NAME", "RTEPORT_INSTANTANEO")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_client: Optional[Client] = None


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def get_client() -> Client:
    global _client
    if not is_configured():
        raise RuntimeError(
            "Supabase não configurado. Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY."
        )
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _client


def _parse_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        if isinstance(value, str) and value.isdigit():
            ts = float(value)
            if ts > 1e12:
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None
    return None


def extract_group_jid(message: dict, chat: dict) -> Optional[str]:
    if message.get("isGroup"):
        return message.get("chatid") or chat.get("wa_chatid")
    chat_id = message.get("chatid") or chat.get("wa_chatid") or ""
    if str(chat_id).endswith("@g.us"):
        return chat_id
    return None


def message_row_from_webhook(payload: dict) -> Optional[dict]:
    message = payload.get("message") or {}
    chat = payload.get("chat") or {}
    group_jid = extract_group_jid(message, chat)
    if not group_jid:
        return None

    message_id = message.get("messageid") or message.get("id")
    if not message_id:
        return None

    text = message.get("text")
    if not text and isinstance(message.get("content"), dict):
        text = message.get("content", {}).get("text")
    if not text and isinstance(message.get("content"), str):
        text = message.get("content")

    return {
        "instance_name": INSTANCE_NAME,
        "group_jid": group_jid,
        "message_id": str(message_id),
        "chat_id": message.get("chatid") or chat.get("wa_chatid"),
        "sender_jid": message.get("sender") or message.get("sender_pn"),
        "sender_name": message.get("senderName") or chat.get("wa_name"),
        "text_content": text,
        "message_type": message.get("messageType") or message.get("type"),
        "from_me": bool(message.get("fromMe")),
        "raw_payload": payload,
        "message_at": _parse_timestamp(message.get("messageTimestamp")),
    }


def message_row_from_uazapi(group_jid: str, item: dict) -> Optional[dict]:
    message_id = item.get("messageid") or item.get("id")
    if not message_id:
        return None

    text = item.get("text")
    if not text and isinstance(item.get("content"), dict):
        text = item.get("content", {}).get("text")
    if not text and isinstance(item.get("content"), str):
        text = item.get("content")

    return {
        "instance_name": INSTANCE_NAME,
        "group_jid": group_jid,
        "message_id": str(message_id),
        "chat_id": item.get("chatid") or group_jid,
        "sender_jid": item.get("sender") or item.get("sender_pn"),
        "sender_name": item.get("senderName"),
        "text_content": text,
        "message_type": item.get("messageType") or item.get("type"),
        "from_me": bool(item.get("fromMe")),
        "raw_payload": item,
        "message_at": _parse_timestamp(item.get("messageTimestamp")),
    }


def upsert_group(group_jid: str, group_name: Optional[str] = None) -> dict:
    client = get_client()
    row = {
        "instance_name": INSTANCE_NAME,
        "group_jid": group_jid,
        "group_name": group_name,
        "monitor": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = (
        client.table("wa_groups")
        .upsert(row, on_conflict="instance_name,group_jid")
        .execute()
    )
    return result.data[0] if result.data else row


def save_message(row: dict) -> dict:
    client = get_client()
    result = (
        client.table("wa_messages")
        .upsert(row, on_conflict="instance_name,message_id")
        .execute()
    )
    return result.data[0] if result.data else row


def save_webhook_message(payload: dict) -> Optional[dict]:
    row = message_row_from_webhook(payload)
    if not row:
        return None
    chat = payload.get("chat") or {}
    upsert_group(row["group_jid"], chat.get("wa_name") or chat.get("name"))
    return save_message(row)


def list_monitored_groups() -> list[dict]:
    client = get_client()
    result = (
        client.table("wa_groups")
        .select("*")
        .eq("instance_name", INSTANCE_NAME)
        .eq("monitor", True)
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data or []


def list_group_messages(group_jid: str, limit: int = 100) -> list[dict]:
    client = get_client()
    result = (
        client.table("wa_messages")
        .select("*")
        .eq("instance_name", INSTANCE_NAME)
        .eq("group_jid", group_jid)
        .order("message_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def save_uazapi_messages(group_jid: str, items: list[dict]) -> int:
    saved = 0
    for item in items:
        row = message_row_from_uazapi(group_jid, item)
        if row:
            save_message(row)
            saved += 1
    return saved
