# RED Alibaba Claude

Gateway direto entre Claude Desktop/Code e endpoints OpenAI-compatible da Alibaba Model Studio.

Objetivo:

- expor API Anthropic-compatible para Claude Desktop e Claude Code;
- usar o melhor das keys que realmente funcionaram;
- combinar **Singapura** para Qwen e **US Virginia** para DeepSeek/Kimi;
- publicar so modelos que passaram em texto e tool calling;
- filtrar `reasoning_content` para manter a UI do Claude limpa.

## Runtime esperado

```text
/opt/redalibabaclaude
/etc/redalibabaclaude.env
/var/lib/redalibabaclaude
redalibabaclaude.service
0.0.0.0:5052
https://redsystems.ddns.net:5052
```

## Endpoints

- `GET /`
- `GET /healthz`
- `GET /v1/models`
- `POST /v1/messages`
- `POST /v1/messages/count_tokens`
- `POST /v1/chat/completions`
- `OPTIONS /*`

## Modelos publicados

- `ALI-SG/qwen-coder-plus`
- `ALI-SG/qwen3.6-plus`
- `ALI-SG/qwen3.6-max-preview`
- `ALI-SG/qwen3-coder-next`
- `ALI-US/qwen3-coder-plus`
- `ALI-US/deepseek-v4-pro`
- `ALI-US/deepseek-v4-flash`
- `ALI-US/kimi-k2.5`

## Observacoes

- `qwen3.6-plus` e `qwen3.6-max-preview` sobem com `enable_thinking=false` para evitar vazamento de pensamento no stream.
- `deepseek-v4-*`, `kimi-k2.5` e `qwen3-coder-next` podem produzir `reasoning_content` no upstream; o gateway remove isso antes de entregar ao Claude.
- os IDs carregam a sigla da regiao no proprio nome:
  - `ALI-SG/*`
  - `ALI-US/*`
- TLS e servido no proprio processo usando os certificados do host.
- autenticacao publica atual: bearer token `red`.

## Rotacao de API key Alibaba

O comando operacional instalado na VM e:

```bash
/usr/local/bin/alibaba
```

Uso normal:

```bash
alibaba sk-nova_chave_alibaba
```

Esse comando:

- atualiza `REDALIBABACLAUDE_SG_API_KEY` e `REDALIBABACLAUDE_US_API_KEY` em `/etc/redalibabaclaude.env`;
- cria backup automatico como `/etc/redalibabaclaude.env.bak.YYYYmmdd-HHMMSS`;
- reinicia `redalibabaclaude.service`;
- se o servico nao voltar ativo, restaura o backup;
- executa `https://127.0.0.1:5052/healthz` com TLS ignorado para validar o processo.

Tambem e possivel trocar so uma regiao:

```bash
alibaba --sg sk-nova_chave_singapura
alibaba --us sk-nova_chave_us
alibaba --show
```

O script fonte fica em `ferramentas/vm/alibaba` e o deploy instala esse arquivo em `/usr/local/bin/alibaba`.
