import os
from typing import Optional

import httpx

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"


def is_configured() -> bool:
    return bool(MISTRAL_API_KEY)


async def generate_group_summary(
    group_name: str,
    messages_text: str,
    extra_instruction: Optional[str] = None,
) -> str:
    if not is_configured():
        raise RuntimeError("MISTRAL_API_KEY não configurada.")

    instruction = extra_instruction or (
        "Faça um resumo completo e bem estruturado do que foi conversado hoje neste grupo."
    )

    system_prompt = """Você é um assistente que gera relatórios diários de grupos WhatsApp.
Regras:
- Escreva em português do Brasil
- Use formatação WhatsApp: *negrito*, _itálico_
- Use emojis relevantes (moderadamente)
- Organize em seções: 📋 *Resumo geral*, 🗣️ *Principais assuntos*, ✅ *Decisões/Ações*, 💡 *Destaques*
- Seja objetivo mas rico em detalhes baseados APENAS nas mensagens fornecidas
- Se houver poucas mensagens, diga isso claramente
- Não invente informações que não estão nas mensagens"""

    user_prompt = f"""Grupo: {group_name}

Instrução: {instruction}

Mensagens do dia:
{messages_text if messages_text.strip() else "(Nenhuma mensagem registrada hoje)"}

Gere o relatório pronto para enviar no WhatsApp."""

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            MISTRAL_API_URL,
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MISTRAL_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.4,
            },
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Mistral API erro {response.status_code}: {response.text}")

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Mistral retornou resposta vazia.")

    return choices[0]["message"]["content"].strip()
