from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
import httpx
import emoji
import os
import logging
from rich.logging import RichHandler
from dotenv import load_dotenv

# Configuração de Logs com Rich
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)

log = logging.getLogger("rich")

# Carrega variáveis de ambiente
load_dotenv()

app = FastAPI(
    title="UAZAPI Helper API",
    description="API para formatar mensagens com emojis e enviar via WhatsApp usando UAZAPI.",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"
)

# Configurações da UAZAPI (Configure estas variáveis no seu ambiente ou arquivo .env)
UAZAPI_BASE_URL = os.getenv("UAZAPI_BASE_URL", "https://free.uazapi.com")
UAZAPI_TOKEN = os.getenv("UAZAPI_TOKEN", "")

class MessagePayload(BaseModel):
    text: str = Field(..., json_schema_extra={"example": "Olá! Teste de emoji :rocket: e *negrito*"})
    number: str = Field(..., json_schema_extra={"example": "5511999999999"})
    instance_token: str = Field(None, description="Opcional: Token da instância UAZAPI")
    subdomain: str = Field("free", description="Subdomínio da UAZAPI (free ou api)")
    linkPreview: bool = Field(False, description="Ativa preview de links")
    linkPreviewTitle: str = Field(None, description="Título personalizado do link")
    linkPreviewDescription: str = Field(None, description="Descrição personalizada do link")
    linkPreviewImage: str = Field(None, description="URL da imagem do link")
    linkPreviewLarge: bool = Field(False, description="Preview grande com upload")
    delay: int = Field(0, description="Atraso em ms (mostra 'Digitando...')")
    mentions: str = Field(None, description="Números para mencionar separados por vírgula")
    async_mode: bool = Field(False, alias="async", description="Envio assíncrono via fila")

    class Config:
        populate_by_name = True

def format_for_whatsapp(text: str) -> str:
    """
    Formata o texto para WhatsApp:
    - Converte aliases de emoji (ex: :smile:) em emojis reais.
    - Suporta formatação padrão do WhatsApp (*negrito*, _itálico_, ~tachado~).
    """
    log.info(f"Formatando texto: [cyan]{text}[/cyan]")
    # Converte aliases de emoji (ex: :rocket: -> 🚀)
    formatted_text = emoji.emojize(text, language='alias')
    return formatted_text

@app.post("/enviar", summary="Enviar mensagem formatada", tags=["WhatsApp"])
async def send_formatted_message(payload: MessagePayload):
    """
    Endpoint aberto para receber texto, formatar e enviar via WhatsApp.
    
    - **text**: Texto com suporte a aliases de emoji (:rocket:) e formatação (*bold*).
    - **number**: Número de destino (DDI + DDD + Número).
    - **instance_token**: (Opcional) Token da instância. Se omitido, usa o configurado no .env.
    """
    # Determina o token da UAZAPI a ser usado
    token = payload.instance_token or UAZAPI_TOKEN
    
    if not token:
        log.error("Token da UAZAPI não encontrado!")
        raise HTTPException(
            status_code=400, 
            detail="Erro: Token da UAZAPI não configurado no servidor nem enviado no payload."
        )
    
    base_url = f"https://{payload.subdomain}.uazapi.com"
    
    # Formata o texto
    formatted_text = format_for_whatsapp(payload.text)
    
    log.info(f"Enviando para o número: [green]{payload.number}[/green]")
    
    # Endpoint da UAZAPI para envio de texto (Corrigido para /send/text)
    url = f"{base_url}/send/text"
    
    headers = {
        "token": token,
        "Content-Type": "application/json"
    }
    
    # Prepara o payload para a UAZAPI incluindo os novos campos
    data = payload.model_dump(exclude={"instance_token", "subdomain", "async_mode"}, exclude_none=True)
    data["text"] = formatted_text
    if payload.async_mode:
        data["async"] = payload.async_mode
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=data, headers=headers)
            
            log.info(f"Resposta UAZAPI: [yellow]{response.status_code}[/yellow]")
            
            return {
                "sucesso": True,
                "texto_enviado": formatted_text,
                "resposta_uazapi": response.json()
            }
        except httpx.HTTPStatusError as e:
            log.error(f"Erro na UAZAPI: {e.response.text}")
            return {
                "sucesso": False,
                "erro": f"Erro na UAZAPI ({e.response.status_code})",
                "detalhes": e.response.text
            }
        except Exception as e:
            log.exception("Erro interno no servidor")
            raise HTTPException(status_code=500, detail=f"Erro interno no servidor: {str(e)}")

@app.get("/", include_in_schema=False)
def read_root():
    return {"message": "UAZAPI Helper API está online!", "swagger_docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    log.info("Iniciando servidor [bold green]UAZAPI Helper[/bold green]...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
