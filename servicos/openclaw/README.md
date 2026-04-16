# OpenClaw na RED Systems

OpenClaw roda na VM unica como um assistente operacional privado da RED Systems.

Ele nao substitui:

- `servicos/redia`
- `servicos/dashboard`
- `servicos/proxy`
- `servicos/redtrader`

Ele fica por cima da stack para:

- operar a VM por chat
- acessar o Control UI/WebChat
- usar nossos modelos do proxy RED
- integrar canais privados, incluindo WhatsApp

## Runtime esperado na VM

- usuario: `openclaw`
- home/state: `/home/openclaw/.openclaw`
- runtime Node dedicado: `/opt/red-openclaw`
- service: `red-openclaw.service`
- gateway local: `127.0.0.1:18789`
- rota publica via nginx: `/openclaw/`

## Curadoria atual de modelos

- texto/tools principal: `ollama/gemini-3-flash-preview`
- fallbacks de texto:
  - `ollama/minimax-m2.1`
  - `ollama/minimax-m2.7`
  - `red/qwen3-next:80b`
- visao principal: `ollama/qwen3-vl:235b-instruct`
- fallbacks de visao:
  - `red/NIM - meta/llama-3.2-11b-vision-instruct`
  - `red/NIM - nvidia/nemotron-nano-12b-v2-vl`

### Observacao sobre imagem

O OpenClaw hoje usa o nosso proxy RED muito bem para:

- texto
- tools
- visao / multimodal

Para **geracao de imagem**, o caminho operacional adotado na RED e um helper de
host que usa o endpoint oficial do proxy RED:

- script: `servicos/openclaw/scripts/red_openclaw_generate_image.py`
- endpoint usado: `http://127.0.0.1:8080/api/images/generate`
- modelo padrao: `NIM - flux.2-klein-4b`

Esse helper:

- gera a imagem via proxy RED
- salva o arquivo em disco
- opcionalmente envia direto pelo WhatsApp do OpenClaw

Exemplo:

```bash
python3 /opt/red-openclaw/helpers/red_openclaw_generate_image.py \
  --prompt "um caranguejo vermelho minimalista em fundo escuro" \
  --output /home/openclaw/.openclaw/media/red-crab.jpg \
  --send-whatsapp +5511999999999 \
  --caption "Teste RED Systems" \
  --json
```

### Comportamento de canal recomendado

- DM do WhatsApp: `open`
- grupos: manter fechados/allowlist por padrao
- tools: `full`
- exec policy: `yolo`

Assim o OpenClaw opera como uma **RED I.A privada**, com acesso amplo ao host,
sem abrir espaco para responder em todo grupo de WhatsApp por acidente.

## Exposicao

O gateway deve ficar em loopback e aparecer publicamente apenas via nginx.

Como a stack atual ainda usa HTTP simples no host publico, a configuracao do Control UI precisa assumir conscientemente um downgrade de seguranca para funcionar fora de localhost/HTTPS.
