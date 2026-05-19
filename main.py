from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
import emoji
import os
import logging
from rich.logging import RichHandler
from dotenv import load_dotenv

from uazapi_client import UazapiClient

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
log = logging.getLogger("rich")

load_dotenv()

# Instância fixa — RTEPORT_INSTANTANEO (painel UAZAPI: onnzetecnologia)
UAZAPI_BASE_URL = os.getenv("UAZAPI_BASE_URL", "https://onnzetecnologia.uazapi.com").rstrip("/")
UAZAPI_TOKEN = os.getenv("UAZAPI_TOKEN", "")
UAZAPI_INSTANCE_NAME = os.getenv("UAZAPI_INSTANCE_NAME", "RTEPORT_INSTANTANEO")

client = UazapiClient(UAZAPI_BASE_URL)

app = FastAPI(
    title="Report Instantâneo — UAZAPI",
    description=(
        f"API dedicada à instância **{UAZAPI_INSTANCE_NAME}**. "
        "Envio de mensagens e webhook exclusivo para o report. "
        "Conexão do WhatsApp e troca de webhook: painel UAZAPI."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


def require_token() -> str:
    if not UAZAPI_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="UAZAPI_TOKEN não configurado no servidor (.env / Render).",
        )
    return UAZAPI_TOKEN


def format_for_whatsapp(text: str) -> str:
    log.info(f"Formatando: [cyan]{text}[/cyan]")
    return emoji.emojize(text, language="alias")


def resolve_destino(number: str | None, group_jid: str | None) -> str:
    destino = (group_jid or number or "").strip()
    if not destino:
        raise HTTPException(
            status_code=422,
            detail="Informe 'number' (contato ou grupo) ou 'group_jid' (ex: 120363...@g.us).",
        )
    return destino


class MessagePayload(BaseModel):
    text: str = Field(..., json_schema_extra={"example": "Relatório :chart: *atualizado*"})
    number: str | None = Field(
        None,
        description="Contato (5511999999999) ou JID do grupo",
    )
    group_jid: str | None = Field(None, examples=["120363012345678901@g.us"])
    linkPreview: bool = False
    linkPreviewTitle: str | None = None
    linkPreviewDescription: str | None = None
    linkPreviewImage: str | None = None
    linkPreviewLarge: bool = False
    delay: int = 0
    mentions: str | None = Field(None, description="Em grupo: 'all' para @todos")
    replyid: str | None = None
    async_mode: bool = Field(False, alias="async")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validar_destino(self):
        if not self.number and not self.group_jid:
            raise ValueError("Informe 'number' ou 'group_jid'.")
        return self


class GroupInfoPayload(BaseModel):
    groupjid: str = Field(..., examples=["120363012345678901@g.us"])


# --- Instância (somente leitura) ---


@app.get("/instancia", summary="Dados da instância fixa", tags=["Instância"])
async def dados_instancia():
    """Retorna nome e URL da instância configurada no servidor (sem expor o token)."""
    return {
        "nome": UAZAPI_INSTANCE_NAME,
        "base_url": UAZAPI_BASE_URL,
        "webhook_dedicado": "/webhook/report",
    }


@app.get("/instancia/status", summary="Status da conexão WhatsApp", tags=["Instância"])
async def status_instancia():
    """disconnected | connecting | connected — conecte pelo painel UAZAPI."""
    token = require_token()
    result = await client.instance_status(token)
    if not result["sucesso"]:
        raise HTTPException(status_code=result["status_code"], detail=result)
    return result["dados"]


# --- Grupos ---


@app.get("/grupos", summary="Grupos desta instância", tags=["Grupos"])
async def listar_grupos():
    """Grupos em que o número da instância RTEPORT_INSTANTANEO participa."""
    token = require_token()
    result = await client.list_groups(token)
    if not result["sucesso"]:
        raise HTTPException(status_code=result["status_code"], detail=result)
    return result["dados"]


@app.post("/grupos/info", summary="Detalhes de um grupo", tags=["Grupos"])
async def info_grupo(payload: GroupInfoPayload):
    token = require_token()
    result = await client.group_info(token, payload.groupjid)
    if not result["sucesso"]:
        raise HTTPException(status_code=result["status_code"], detail=result)
    return result["dados"]


# --- Envio ---


@app.post("/enviar", summary="Enviar mensagem (contato ou grupo)", tags=["Mensagens"])
async def enviar_mensagem(payload: MessagePayload):
    """
    Envia pela instância **RTEPORT_INSTANTANEO** apenas.

    - Contato: `number` = `5511999999999`
    - Grupo: `group_jid` ou `number` = `120363...@g.us` (veja GET /grupos)
    """
    token = require_token()
    destino = resolve_destino(payload.number, payload.group_jid)
    formatted_text = format_for_whatsapp(payload.text)

    log.info(f"[{UAZAPI_INSTANCE_NAME}] Enviando → [green]{destino}[/green]")

    data = payload.model_dump(
        exclude={"async_mode", "group_jid", "number", "text"},
        exclude_none=True,
    )
    data["number"] = destino
    data["text"] = formatted_text
    if payload.async_mode:
        data["async"] = True

    result = await client.send_text(token, data)
    if not result["sucesso"]:
        raise HTTPException(status_code=result["status_code"], detail=result)

    return {
        "sucesso": True,
        "instancia": UAZAPI_INSTANCE_NAME,
        "destino": destino,
        "texto_enviado": formatted_text,
        "resposta_uazapi": result["dados"],
    }


# --- Webhook dedicado ao report ---


@app.post(
    "/webhook/report",
    summary="Webhook exclusivo do Report (configurar no painel UAZAPI)",
    tags=["Webhook"],
    include_in_schema=True,
)
async def webhook_report(request: Request):
    """
    URL para cadastrar no painel da instância **RTEPORT_INSTANTANEO**:

    `https://SEU-DOMINIO-RENDER/webhook/report`

    Eventos sugeridos: `messages`, `connection`, `message_status`.
    Não compartilhe esta URL com outros processos — é só deste report.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    incoming_token = payload.get("token")
    if incoming_token and incoming_token != UAZAPI_TOKEN:
        log.warning("Webhook rejeitado: token não corresponde à instância do report")
        raise HTTPException(status_code=403, detail="Token da instância inválido")

    event_type = payload.get("EventType") or payload.get("event") or "unknown"
    message = payload.get("message") or {}
    chat = payload.get("chat") or {}

    log.info(
        f"[webhook/report] {UAZAPI_INSTANCE_NAME} | "
        f"evento={event_type} | "
        f"grupo={message.get('isGroup')} | "
        f"de={message.get('senderName') or chat.get('wa_name')}"
    )

    # Ponto de extensão: processar relatório aqui (mensagens recebidas, etc.)
    return {"ok": True, "instancia": UAZAPI_INSTANCE_NAME, "evento": event_type}


@app.get("/webhook/report/info", summary="Como configurar o webhook no painel", tags=["Webhook"])
def webhook_info():
    """Instruções para não misturar com outros webhooks do mesmo servidor UAZAPI."""
    return {
        "instancia": UAZAPI_INSTANCE_NAME,
        "base_url_uazapi": UAZAPI_BASE_URL,
        "caminho_webhook": "/webhook/report",
        "exemplo_url_render": "https://uazapi-helper.onrender.com/webhook/report",
        "eventos_recomendados": ["messages", "connection", "message_status"],
        "observacao": (
            "Configure apenas na instância RTEPORT_INSTANTANEO no painel UAZAPI. "
            "Outras instâncias/processos devem usar outra URL de webhook."
        ),
    }


@app.get("/", include_in_schema=False)
def read_root():
    return {
        "app": "Report Instantâneo",
        "instancia": UAZAPI_INSTANCE_NAME,
        "uazapi": UAZAPI_BASE_URL,
        "docs": "/docs",
        "webhook": "/webhook/report",
        "enviar": "POST /enviar",
    }


if __name__ == "__main__":
    import uvicorn

    log.info(f"Iniciando report — instância [bold]{UAZAPI_INSTANCE_NAME}[/bold]")
    uvicorn.run(app, host="0.0.0.0", port=8000)
