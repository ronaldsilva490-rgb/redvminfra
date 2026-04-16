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

## Curadoria inicial de modelos

- texto/tools principal: `red/qwen3-next:80b`
- fallbacks de texto:
  - `red/deepseek-v3.2`
  - `red/glm-5.1`
  - `red/kimi-k2.5`
- visao principal: `red/qwen3-vl:235b-instruct`
- fallbacks de visao:
  - `red/NIM - meta/llama-3.2-11b-vision-instruct`
  - `red/NIM - nvidia/nemotron-nano-12b-v2-vl`
  - `red/NIM - microsoft/phi-4-multimodal-instruct`

## Exposicao

O gateway deve ficar em loopback e aparecer publicamente apenas via nginx.

Como a stack atual ainda usa HTTP simples no host publico, a configuracao do Control UI precisa assumir conscientemente um downgrade de seguranca para funcionar fora de localhost/HTTPS.
