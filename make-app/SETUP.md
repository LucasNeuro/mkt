# Como montar o app no Make — passo a passo

Os arquivos em `make-app/` **não são enviados** para o Make. Você **abre cada arquivo no Cursor**, **copia** o JSON e **cola** na aba correspondente do editor do Make.

**Antes de começar:** sua API precisa estar no ar (Render ou local com ngrok). A connection testa `GET /instancia`.

---

## PASSO 0 — Entrar no editor

1. Acesse [make.com](https://www.make.com) → login  
2. Menu lateral: **More** → **Custom Apps** (ou **Apps** → Custom Apps)  
3. **+ Create app** (canto superior direito)

---

## PASSO 1 — Criar o app

Preencha e clique **Save**:

| Campo | Valor |
|--------|--------|
| Name | `report-instantaneo` |
| Label | `Report Instantâneo` |
| Description | WhatsApp Report — RTEPORT_INSTANTANEO |
| Theme | `#25D366` |
| Language | Portuguese |
| Audience | Global |

Você entra na tela do app com menu à esquerda: **Connections**, **Base**, **Webhooks**, **Modules**, etc.

---

## PASSO 2 — Connection

1. Clique **Connections** (menu esquerdo)  
2. **+ Create Connection**  
3. Preencha:
   - **Label:** `Report API`
   - **Type:** `API Key` (só usamos o campo URL; token UAZAPI fica no Render)
4. **Save**

### Aba Parameters

1. Apague o código padrão que vier  
2. Abra no projeto: `make-app/connection/parameters.json`  
3. Copie tudo → cole → **Save changes**

### Aba Communication

1. Apague o código padrão  
2. Abra: `make-app/connection/communication.json`  
3. Copie → cole → **Save changes**

### Testar a connection (importante)

1. No Make, vá em **Connections** (menu principal da conta, não do app)  
2. **Add** → escolha **Report Instantâneo** → **Report API**  
3. **URL da API Report:** `https://SEU-APP.onrender.com` (sem `/` no final)  
4. **Save** — deve conectar e mostrar `RTEPORT_INSTANTANEO` nos metadados  

Se falhar: API offline, URL errada ou Render sem `UAZAPI_TOKEN`.

---

## PASSO 3 — Base

1. Menu esquerdo do app → **Base**  
2. Aba **Communication**  
3. Apague o padrão  
4. Abra: `make-app/base/communication.json`  
5. Copie → cole → **Save changes**

---

## PASSO 4 — Webhook (para o gatilho WhatsApp)

1. Menu esquerdo → **Webhooks**  
2. **+ Create Webhook**  
3. Preencha:
   - **Label:** `WhatsApp UAZAPI`
   - **Type:** `Dedicated`
   - **Attachment:** `Not attached` (usuário cola URL no painel UAZAPI)
4. **Save** (não precisa colar JSON aqui)

---

## PASSO 5 — Módulo 1: Send WhatsApp Message (ação)

1. **Modules** → **+ Create Module**  
2. Preencha:

| Campo | Valor |
|--------|--------|
| Template | Blank module |
| Type | **Action** |
| Connection | Report API |
| Name | `sendMessage` |
| Label | `Send WhatsApp Message` |
| Description | Envia mensagem via API Report |

3. **Save**

### Aba Mappable parameters

Cole de: `make-app/modules/sendMessage/mappable-parameters.json` → **Save changes**

### Aba Communication

Cole de: `make-app/modules/sendMessage/communication.json` → **Save changes**

### Aba Interface

Cole de: `make-app/modules/sendMessage/interface.json` → **Save changes**

---

## PASSO 6 — Módulo 2: List WhatsApp Groups

1. **+ Create Module**  
2. Type: **Search** | Connection: Report API | Name: `listGroups` | Label: `List WhatsApp Groups`  
3. **Save**

| Aba | Arquivo |
|-----|---------|
| Mappable parameters | `modules/listGroups/mappable-parameters.json` (vazio `[]`) |
| Communication | `modules/listGroups/communication.json` |

---

## PASSO 7 — Módulo 3: Get Connection Status

1. **+ Create Module**  
2. Type: **Action** | Name: `getStatus` | Label: `Get Connection Status`  
3. **Save**

| Aba | Arquivo |
|-----|---------|
| Mappable parameters | `modules/getStatus/mappable-parameters.json` |
| Communication | `modules/getStatus/communication.json` |

---

## PASSO 8 — Módulo 4: Watch WhatsApp Event (gatilho)

1. **+ Create Module**  
2. Preencha:

| Campo | Valor |
|--------|--------|
| Type | **Instant trigger (webhook)** |
| Webhook | **WhatsApp UAZAPI** (criado no passo 4) |
| Connection | Report API |
| Name | `watchWhatsApp` |
| Label | `Watch WhatsApp Event` |

3. **Save**

| Aba | O que colar |
|-----|-------------|
| Communication | `{}` (objeto vazio) |
| Static parameters | `[]` |
| Mappable parameters | `[]` |
| Interface | `modules/watchWhatsApp/interface.json` |
| Samples | `modules/watchWhatsApp/samples.json` |

---

## PASSO 9 — Publicar o app

1. No app, menu superior → **Publish** (ou ícone de publicar)  
2. Confirme a publicação  
3. O app **Report Instantâneo** aparece ao criar cenários

---

## PASSO 10 — Usar em um cenário

1. **Scenarios** → **+ Create a new scenario**  
2. Clique o **+** → procure **Report Instantâneo**  
3. Escolha **Watch WhatsApp Event**  
4. **Create a webhook** → copie a URL `https://hook....make.com/...`  
5. Painel UAZAPI → **RTEPORT_INSTANTANEO** → **Configurar Webhook** → cole a URL do Make  
6. Eventos: `messages`, `connection`, `message_status`  
7. Adicione módulo **Send WhatsApp Message**  
8. Connection: mesma **Report API** (URL do Render)  
9. Mapeie: Mensagem = texto desejado | Grupo JID = `{{message.chatid}}`  
10. **Run once** para testar

---

## Resumo visual

```
Custom App editor (Make)
├── Connections  ← parameters.json + communication.json
├── Base         ← base/communication.json
├── Webhooks     ← Dedicated Not attached (sem JSON)
└── Modules
    ├── sendMessage      (Action)
    ├── listGroups       (Search)
    ├── getStatus        (Action)
    └── watchWhatsApp    (Instant trigger + interface + samples)
```

---

## Erros comuns

| Problema | Solução |
|----------|---------|
| Connection falha | API no Render rodando; URL sem barra final |
| Módulo não aparece no cenário | Publicar o app (Passo 9) |
| Gatilho não dispara | URL do Make no painel UAZAPI; WhatsApp `connected` |
| Envio falha 500 | `UAZAPI_TOKEN` no Render; instância conectada |

Documentação Make: https://developers.make.com/custom-apps-documentation
