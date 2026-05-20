import os
import re
import logging
from typing import Any, Optional

import emoji

import mistral_service
import storage
from uazapi_client import UazapiClient

log = logging.getLogger("rich")

GROUPS_PER_PAGE = 15

LIST_GROUPS_COMMANDS = (
    "report",
    "grupos",
    "resumo",
    "menu",
    "inicio",
    "início",
    "listar grupos",
    "listar",
)

ADMIN_PHONES = {
    storage.normalize_phone(p.strip())
    for p in os.getenv("ADMIN_PHONES", "").split(",")
    if p.strip()
}


def is_admin(phone: str) -> bool:
    if not ADMIN_PHONES:
        return False
    return storage.normalize_phone(phone) in ADMIN_PHONES


def extract_sender_phone(payload: dict) -> str:
    message = payload.get("message") or {}
    for key in ("sender_pn", "sender"):
        phone = storage.normalize_phone(message.get(key))
        if phone:
            return phone
    chat = payload.get("chat") or {}
    return storage.normalize_phone(chat.get("phone"))


def extract_chat_dest_phone(payload: dict) -> str:
    message = payload.get("message") or {}
    chat = payload.get("chat") or {}
    return storage.normalize_phone(
        message.get("chatid") or chat.get("wa_chatid") or chat.get("phone") or ""
    )


def extract_admin_actor_phone(payload: dict) -> str:
    """Número do admin que está comandando (inclui 'Conversar comigo mesmo')."""
    message = payload.get("message") or {}
    if message.get("fromMe"):
        owner = storage.normalize_phone(
            message.get("owner") or message.get("sender_pn") or message.get("sender") or ""
        )
        if owner:
            return owner
    return extract_sender_phone(payload)


def is_admin_self_chat(payload: dict) -> bool:
    """WhatsApp 'Mensagens salvas' / conversar comigo mesmo no mesmo aparelho."""
    message = payload.get("message") or {}
    if not message.get("fromMe") or message.get("isGroup"):
        return False
    owner = extract_admin_actor_phone(payload)
    if not owner or not is_admin(owner):
        return False
    return extract_chat_dest_phone(payload) == owner


def extract_reply_dest(payload: dict) -> str:
    message = payload.get("message") or {}
    chat = payload.get("chat") or {}
    return (
        message.get("chatid")
        or chat.get("wa_chatid")
        or message.get("sender")
        or message.get("sender_pn")
        or ""
    )


def extract_message_text(payload: dict) -> str:
    message = payload.get("message") or {}
    text = (message.get("text") or "").strip()
    if not text and isinstance(message.get("content"), dict):
        text = (message.get("content", {}).get("text") or "").strip()
    if not text and isinstance(message.get("content"), str):
        text = message.get("content", "").strip()
    return text


def is_private_admin_message(payload: dict) -> bool:
    message = payload.get("message") or {}
    if message.get("isGroup"):
        return False
    if message.get("fromMe"):
        return is_admin_self_chat(payload)
    sender = extract_sender_phone(payload)
    return is_admin(sender)


def extract_groups_list(data: Any) -> list[dict]:
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = None
        for key in ("groups", "data", "items", "result"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
        if items is None:
            items = [data] if data.get("jid") or data.get("JID") else []
    else:
        return []

    groups: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        jid = item.get("jid") or item.get("JID") or item.get("id") or item.get("groupjid")
        if not jid or not str(jid).endswith("@g.us"):
            continue
        name = (
            item.get("Name")
            or item.get("name")
            or item.get("subject")
            or item.get("groupName")
            or jid
        )
        groups.append({"jid": str(jid), "name": str(name)})
    return dedupe_sort_groups(groups)


def dedupe_sort_groups(groups: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for group in groups:
        jid = group.get("jid") or ""
        if not jid or jid in seen:
            continue
        seen.add(jid)
        unique.append(group)
    return sorted(unique, key=lambda g: (g.get("name") or "").casefold())


def parse_group_step(step: str) -> tuple[bool, int]:
    if step == "selecting_group":
        return True, 0
    if step.startswith("selecting_group:"):
        try:
            return True, max(0, int(step.split(":", 1)[1]))
        except ValueError:
            return True, 0
    return False, 0


def group_step_name(page: int) -> str:
    return f"selecting_group:{page}"


def format_groups_page(groups: list[dict], page: int) -> str:
    total = len(groups)
    total_pages = max(1, (total + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
    page = min(max(page, 0), total_pages - 1)
    start = page * GROUPS_PER_PAGE
    chunk = groups[start : start + GROUPS_PER_PAGE]

    lines = [
        f"📂 *Grupos disponíveis* ({total} total)",
        f"Página *{page + 1}* de *{total_pages}*\n",
    ]
    for i, group in enumerate(chunk, start=start + 1):
        lines.append(f"*{i}.* {group['name']}")

    lines.append("\nResponda com o *número* do grupo para o resumo de *hoje*.")
    if page + 1 < total_pages:
        lines.append("• *mais* — próxima página")
    if page > 0:
        lines.append("• *anterior* — página anterior")
    lines.append("• *cancelar* — voltar ao início")
    return "\n".join(lines)


async def send_whatsapp_text(client: UazapiClient, token: str, dest: str, text: str) -> bool:
    formatted = emoji.emojize(text, language="alias")
    result = await client.send_text(token, {"number": dest, "text": formatted})
    return result.get("sucesso", False)


async def send_whatsapp_poll(
    client: UazapiClient, token: str, dest: str, question: str, options: list[str]
) -> bool:
    result = await client.send_poll(
        token,
        {
            "number": dest,
            "question": question,
            "options": options,
        },
    )
    return result.get("sucesso", False)


async def generate_and_send_summary(
    client: UazapiClient,
    token: str,
    admin_phone: str,
    group_jid: str,
    group_name: str,
    reply_dest: str,
) -> dict:
    messages = storage.list_group_messages_today(group_jid)
    messages_text = storage.format_messages_for_ai(messages)

    summary = await mistral_service.generate_group_summary(group_name, messages_text)
    summary = emoji.emojize(summary, language="alias")

    storage.save_summary(
        group_jid=group_jid,
        group_name=group_name,
        content=summary,
        message_count=len(messages),
        requested_by=admin_phone,
        sent_to_group=False,
        poll_sent=False,
    )

    sent_text = await send_whatsapp_text(client, token, group_jid, summary)
    poll_sent = await send_whatsapp_poll(
        client,
        token,
        group_jid,
        "Como foi o dia no grupo? :star2:",
        ["Excelente :thumbsup:", "Bom :ok_hand:", "Precisa melhorar :chart:"],
    )

    storage.save_summary(
        group_jid=group_jid,
        group_name=group_name,
        content=summary,
        message_count=len(messages),
        requested_by=admin_phone,
        sent_to_group=sent_text,
        poll_sent=poll_sent,
    )

    status = "✅ *Resumo enviado!*" if sent_text else "⚠️ Resumo gerado, mas falhou o envio."
    if poll_sent:
        status += "\n📊 Enquete enviada no grupo."
    else:
        status += "\n⚠️ Enquete não enviada."

    await send_whatsapp_text(
        client,
        token,
        reply_dest,
        f"{status}\n\n*Grupo:* {group_name}\n*Mensagens usadas:* {len(messages)}",
    )

    return {
        "group_jid": group_jid,
        "group_name": group_name,
        "message_count": len(messages),
        "sent_to_group": sent_text,
        "poll_sent": poll_sent,
    }


async def handle_admin_command(
    payload: dict,
    client: UazapiClient,
    token: str,
) -> Optional[dict]:
    if not storage.is_configured():
        return None
    if not is_private_admin_message(payload):
        return None
    if not mistral_service.is_configured():
        dest = extract_reply_dest(payload)
        if dest:
            await send_whatsapp_text(
                client, token, dest, "⚠️ IA não configurada (MISTRAL_API_KEY)."
            )
        return {"erro": "mistral_nao_configurada"}

    admin_phone = extract_admin_actor_phone(payload)
    reply_dest = extract_reply_dest(payload)
    text = extract_message_text(payload).lower().strip()
    cmd = re.sub(r"\s+", " ", text)

    if not reply_dest:
        return {"erro": "destino_resposta_invalido"}

    session = storage.get_session(admin_phone) or {"step": "idle"}
    step = session.get("step", "idle")

    if cmd in ("cancelar", "sair", "menu"):
        storage.clear_session(admin_phone)
        await send_whatsapp_text(
            client,
            token,
            reply_dest,
            "📋 *Report Instantâneo*\n\n"
            "Comandos:\n"
            "• *report* ou *grupos* — listar grupos\n"
            "• *1*, *2*... — escolher grupo e gerar resumo do dia\n"
            "• *mais* / *anterior* — navegar na lista de grupos\n"
            "• *historico* — ver resumos salvos\n"
            "• *cancelar* — voltar ao início",
        )
        return {"comando": "menu"}

    if cmd in ("historico", "histórico", "resumos"):
        summaries = storage.list_summaries(limit=5)
        if not summaries:
            await send_whatsapp_text(client, token, reply_dest, "Nenhum resumo salvo ainda.")
            return {"comando": "historico", "total": 0}
        lines = ["📚 *Últimos resumos:*\n"]
        for s in summaries:
            lines.append(
                f"• {s.get('summary_date')} — {s.get('group_name') or s.get('group_jid')}"
            )
        await send_whatsapp_text(client, token, reply_dest, "\n".join(lines))
        return {"comando": "historico", "total": len(summaries)}

    if cmd in LIST_GROUPS_COMMANDS:
        result = await client.list_groups(token)
        if not result.get("sucesso"):
            await send_whatsapp_text(
                client, token, reply_dest, "❌ Erro ao listar grupos. Instância conectada?"
            )
            return {"erro": "list_groups_falhou"}

        groups = extract_groups_list(result.get("dados"))
        if not groups:
            await send_whatsapp_text(client, token, reply_dest, "Nenhum grupo encontrado.")
            return {"grupos": 0}

        storage.upsert_session(
            admin_phone,
            step=group_step_name(0),
            pending_groups=groups,
            selected_group_jid=None,
            selected_group_name=None,
        )

        await send_whatsapp_text(
            client, token, reply_dest, format_groups_page(groups, 0)
        )
        return {"comando": "listar_grupos", "total": len(groups), "pagina": 1}

    is_selecting, page = parse_group_step(step)
    pending = session.get("pending_groups") or []

    if is_selecting and cmd in ("mais", "proximo", "próximo", "next"):
        if not pending:
            await send_whatsapp_text(
                client, token, reply_dest, "Envie *report* para listar os grupos."
            )
            return {"erro": "sem_grupos_pendentes"}
        total_pages = max(1, (len(pending) + GROUPS_PER_PAGE - 1) // GROUPS_PER_PAGE)
        new_page = min(page + 1, total_pages - 1)
        storage.upsert_session(admin_phone, step=group_step_name(new_page), pending_groups=pending)
        await send_whatsapp_text(
            client, token, reply_dest, format_groups_page(pending, new_page)
        )
        return {"comando": "pagina_grupos", "pagina": new_page + 1, "total": len(pending)}

    if is_selecting and cmd in ("anterior", "prev"):
        if not pending:
            await send_whatsapp_text(
                client, token, reply_dest, "Envie *report* para listar os grupos."
            )
            return {"erro": "sem_grupos_pendentes"}
        new_page = max(page - 1, 0)
        storage.upsert_session(admin_phone, step=group_step_name(new_page), pending_groups=pending)
        await send_whatsapp_text(
            client, token, reply_dest, format_groups_page(pending, new_page)
        )
        return {"comando": "pagina_grupos", "pagina": new_page + 1, "total": len(pending)}

    if is_selecting and cmd.isdigit():
        idx = int(cmd) - 1
        if idx < 0 or idx >= len(pending):
            await send_whatsapp_text(client, token, reply_dest, "Número inválido. Tente de novo.")
            return {"erro": "indice_invalido"}

        group = pending[idx]
        group_jid = group["jid"]
        group_name = group["name"]

        storage.upsert_session(
            admin_phone,
            step="idle",
            selected_group_jid=group_jid,
            selected_group_name=group_name,
            pending_groups=pending,
        )

        await send_whatsapp_text(
            client,
            token,
            reply_dest,
            f"⏳ Gerando resumo de *hoje* para:\n*{group_name}*\n\nAguarde...",
        )

        try:
            result = await generate_and_send_summary(
                client, token, admin_phone, group_jid, group_name, reply_dest
            )
            return {"comando": "resumo_gerado", **result}
        except Exception as e:
            log.exception("Erro ao gerar resumo")
            await send_whatsapp_text(
                client, token, reply_dest, f"❌ Erro ao gerar resumo: {str(e)}"
            )
            return {"erro": str(e)}

    await send_whatsapp_text(
        client,
        token,
        reply_dest,
        "Comando não reconhecido. Envie *report* para listar grupos ou *cancelar*.",
    )
    return {"comando": "desconhecido", "texto": cmd}
