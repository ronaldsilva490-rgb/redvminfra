# REDIA

REDIA e o runtime principal da **RED I.A**.

Ela nao deve mais ser pensada como “servico solto de outra VM”. Hoje ela faz parte da stack da **VM unica** e conversa diretamente com o dashboard principal.

## O que ela faz

- conexao WhatsApp via Baileys
- SQLite local para config, conversas, memoria e agenda
- proxy RED como backend IA principal
- analise de imagem e transcricao de audio
- TTS com Edge
- dashboard/runtime proprio em `/redia/`
- integracao com o dashboard principal em `/dashboard/redia`

## Start local

```bash
cp .env.example .env
npm install
npm start
```

Runtime:

```text
http://localhost:3099
```

## Papel no dashboard principal

A integracao no dashboard principal deve suportar:

- status do runtime
- status do WhatsApp
- configuracao
- conversas
- envio manual
- schedules
- teste de IA
- benchmark

Se essa integracao quebrar, verifique primeiro:

1. `REDIA_ADMIN_TOKEN`
2. `REDIA_URL`
3. conectividade entre dashboard e runtime

## Model roles

Separacao atual por funcao:

- `chat.default_model`: conversa principal
- `chat.vision_model`: analise de imagem
- `learning.model`: resumo/fatos/perfil
- `proactive.model`: participacao espontanea

## Observacoes

- o runtime proprio da REDIA continua vivo;
- o centro operacional da stack, porem, e o dashboard principal;
- nao trate o painel standalone como unica fonte da verdade.
