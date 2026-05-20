import os
from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from supabase import Client, create_client

INSTANCE_NAME = os.getenv("UAZAPI_INSTANCE_NAME", "RTEPORT_INSTANTANEO")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "America/Sao_Paulo"))

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


def normalize_phone(value: str | None) -> str:
    if not value:
        return ""
    base = str(value).split("@")[0]
    return "".join(c for c in base if c.isdigit())


def today_local() -> date:
    return datetime.now(TZ).date()


def _today_start_iso() -> str:
    start = datetime.combine(today_local(), datetime.min.time(), tzinfo=TZ)
    return start.astimezone(timezone.utc).isoformat()


def get_session(admin_phone: str) -> Optional[dict]:
    client = get_client()
    result = (
        client.table("wa_sessions")
        .select("*")
        .eq("instance_name", INSTANCE_NAME)
        .eq("admin_phone", admin_phone)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def upsert_session(admin_phone: str, **fields: Any) -> dict:
    client = get_client()
    row = {
        "instance_name": INSTANCE_NAME,
        "admin_phone": admin_phone,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    result = (
        client.table("wa_sessions")
        .upsert(row, on_conflict="instance_name,admin_phone")
        .execute()
    )
    return result.data[0] if result.data else row


def clear_session(admin_phone: str) -> None:
    client = get_client()
    client.table("wa_sessions").delete().eq("instance_name", INSTANCE_NAME).eq(
        "admin_phone", admin_phone
    ).execute()


def list_group_messages_today(group_jid: str, limit: int = 500) -> list[dict]:
    client = get_client()
    start = _today_start_iso()
    result = (
        client.table("wa_messages")
        .select("*")
        .eq("instance_name", INSTANCE_NAME)
        .eq("group_jid", group_jid)
        .gte("message_at", start)
        .order("message_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data or []


def format_messages_for_ai(messages: list[dict]) -> str:
    lines: list[str] = []
    for msg in messages:
        text = (msg.get("text_content") or "").strip()
        if not text:
            continue
        sender = msg.get("sender_name") or msg.get("sender_jid") or "Desconhecido"
        ts = msg.get("message_at") or ""
        time_part = ts[11:16] if len(ts) >= 16 else "??:??"
        lines.append(f"[{time_part}] {sender}: {text}")
    return "\n".join(lines) if lines else ""


def save_summary(
    group_jid: str,
    group_name: str | None,
    content: str,
    message_count: int,
    requested_by: str,
    sent_to_group: bool = False,
    poll_sent: bool = False,
    summary_date: date | None = None,
) -> dict:
    client = get_client()
    day = summary_date or today_local()
    row = {
        "instance_name": INSTANCE_NAME,
        "group_jid": group_jid,
        "group_name": group_name,
        "summary_date": day.isoformat(),
        "content": content,
        "message_count": message_count,
        "requested_by": requested_by,
        "sent_to_group": sent_to_group,
        "poll_sent": poll_sent,
    }
    result = (
        client.table("wa_summaries")
        .upsert(row, on_conflict="instance_name,group_jid,summary_date")
        .execute()
    )
    return result.data[0] if result.data else row


def list_summaries(group_jid: str | None = None, limit: int = 30) -> list[dict]:
    client = get_client()
    query = (
        client.table("wa_summaries")
        .select("*")
        .eq("instance_name", INSTANCE_NAME)
        .order("summary_date", desc=True)
        .limit(limit)
    )
    if group_jid:
        query = query.eq("group_jid", group_jid)
    result = query.execute()
    return result.data or []
