# Servicos

Codigo dos servicos vivos ou ainda uteis da RED Systems.

```text
proxy/        Proxy IA Ollama-compatible com roteamento NVIDIA.
proxy-lab/    Laboratorio Groq + Mistral para benchmark pago.
dashboard/    Painel Red VM / Red Systems.
redia/        IA de WhatsApp standalone.
redtrader/    Painel paper/demo de trading.
extensao-iq-demo/ Extensao Chrome MV3 para ler a IQ demo em tempo real.
deploy-agent/ Webhook/deploy inteligente legado.
```

Cada servico deve manter seu proprio `.env.example`, dependencias e README quando houver. Dados runtime ficam em `data/` e sao ignorados pelo Git.
