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

- texto/tools principal: `ollama/minimax-m2.1`
- fallbacks de texto:
  - `ollama/minimax-m2.7`
  - `ollama/kimi-k2.5`
  - `red/qwen3-next:80b`
- visao principal: `red/NIM - meta/llama-3.2-11b-vision-instruct`
- fallbacks de visao:
  - `red/NIM - nvidia/nemotron-nano-12b-v2-vl`
  - `red/qwen3-vl:235b-instruct`

### Observacao sobre imagem

O OpenClaw hoje usa o nosso proxy RED muito bem para:

- texto
- tools
- visao / multimodal

Mas **geracao de imagem** dentro do `openclaw capability image generate` ainda
nao ficou plug-and-play via proxy RED. O runtime do OpenClaw continua tratando
geracao como providers dedicados (`openai`, `google`, `fal`, `minimax`,
`comfy`, `vydra`), e isso precisa ser configurado de forma nativa no proprio
OpenClaw ou por um provedor externo compativel.

## Exposicao

O gateway deve ficar em loopback e aparecer publicamente apenas via nginx.

Como a stack atual ainda usa HTTP simples no host publico, a configuracao do Control UI precisa assumir conscientemente um downgrade de seguranca para funcionar fora de localhost/HTTPS.
