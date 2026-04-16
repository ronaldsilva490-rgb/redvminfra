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

- texto/tools principal: `red/NIM - nvidia/llama-3.1-nemotron-nano-8b-v1`
- fallback operacional de texto/tools:
  - `red/NIM - nvidia/nemotron-mini-4b-instruct`
- fallback de seguranca:
  - `ollama/minimax-m2.1`
- visao principal: `red/NIM - meta/llama-3.2-11b-vision-instruct`
- fallback rapido de visao:
  - `red/NIM - nvidia/nemotron-nano-12b-v2-vl`
- fallback pesado de visao:
  - `red/qwen3-vl:235b-instruct`

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
- fallback automatico: `NIM - flux.1-schnell`

Esse helper:

- gera a imagem via proxy RED
- salva o arquivo em disco
- opcionalmente envia direto pelo WhatsApp do OpenClaw
- tenta primeiro o modelo mais detalhado
- se ele falhar, cai no fallback rapido automaticamente

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

## Leitura pratica da curadoria

- `llama-3.1-nemotron-nano-8b-v1`
  - melhor equilibrio real para OpenClaw quando o assunto e **texto + tools + baixa latencia**
- `nemotron-mini-4b-instruct`
  - fallback que ainda faz tool call direito, mas pode demorar bastante mais
- `llama-3.2-11b-vision-instruct`
  - melhor NIM de visao no equilibrio **precisao + tempo**
- `nemotron-nano-12b-v2-vl`
  - visao mais rapida, boa para fallback
- `flux.2-klein-4b`
  - melhor NIM de imagem para detalhe/qualidade geral
- `flux.1-schnell`
  - melhor fallback de imagem quando a prioridade e responder logo

Assim o OpenClaw opera como uma **RED I.A privada**, com acesso amplo ao host,
sem abrir espaco para responder em todo grupo de WhatsApp por acidente.

## Exposicao

O gateway deve ficar em loopback e aparecer publicamente apenas via nginx.

Como a stack atual ainda usa HTTP simples no host publico, a configuracao do Control UI precisa assumir conscientemente um downgrade de seguranca para funcionar fora de localhost/HTTPS.
