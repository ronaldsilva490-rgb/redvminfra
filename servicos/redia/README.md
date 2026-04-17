# REDIA

REDIA e o runtime principal da RED I.A na VM unica.

## O que este servico entrega

- rota publica: `/redia/`
- runtime WhatsApp via Baileys
- SQLite local para memoria, conversas, agenda e configuracao
- consumo do proxy RED para texto e visao
- TTS por Edge
- integracao com o dashboard principal em `/dashboard/redia`

## Dependencias do host

- Node.js 20+
- npm
- `ffmpeg` para audio e TTS
- biblioteca nativa compativel com `better-sqlite3`

## Variaveis de ambiente

```bash
cp .env.example .env
```

As mais importantes:

- `REDIA_PORT`
- `REDIA_ADMIN_TOKEN`
- `REDIA_PROXY_URL`
- `REDIA_DEFAULT_MODEL`
- `REDIA_VISION_MODEL`
- `REDIA_LEARNING_MODEL`
- `REDIA_PROACTIVE_MODEL`

## Rodar localmente

```bash
cd servicos/redia
cp .env.example .env
npm install
npm start
```

Abra:

```text
http://127.0.0.1:3099
```

## Instalacao em qualquer VM

1. Instale dependencias:

```bash
apt-get update
apt-get install -y nodejs npm ffmpeg
```

2. Copie o runtime:

```bash
mkdir -p /opt/redia
rsync -a servicos/redia/ /opt/redia/
cd /opt/redia
npm install
```

3. Crie o ambiente:

```bash
cp /opt/redia/.env.example /opt/redia/.env
```

4. Ajuste os valores reais, especialmente:

- `REDIA_ADMIN_TOKEN`
- `REDIA_PROXY_URL`
- modelos padrao

5. Instale a unit:

```bash
cp infraestrutura/systemd/redia.service /etc/systemd/system/redia.service
systemctl daemon-reload
systemctl enable --now redia
```

6. Exponha `/redia/` pelo nginx com o snippet oficial.

## Validacao recomendada

```bash
cd /opt/redia && npm run check
systemctl is-active redia
curl http://127.0.0.1:3099/api/status
```

## Papel no dashboard principal

A integracao do dashboard principal precisa continuar suportando:

- status do runtime
- status do WhatsApp
- configuracao
- conversas
- envio manual
- schedules
- teste de IA
- benchmark

Se quebrar, confira primeiro:

1. `REDIA_ADMIN_TOKEN`
2. `REDIA_URL`
3. conectividade entre dashboard e runtime

## Runtime oficial na RED

- codigo: `/opt/redia`
- data: `/opt/redia/data`
- service: `redia.service`
- publicacao: `/redia/`

## Observacoes

- O runtime proprio da REDIA continua vivo, mas a operacao diaria deve convergir para o dashboard principal.
- Nao trate o painel standalone como unica fonte da verdade.
