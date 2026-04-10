# RED Model Studio

App desktop em Python + PySide6 para testar o proxy oficial da RED Systems.

## O que ele faz

- ping em ms para a VM/proxy em tempo quase real
- catalogo vivo de modelos do proxy
- chat completo com streaming
- thinking separado quando o modelo expuser raciocinio
- metricas reais da resposta:
  - tempo total
  - primeiro token
  - prompt tokens
  - completion tokens
  - tokens por segundo
  - finish reason
- aba de geracao de imagens com preview e salvamento

## Execucao

Na raiz do repo:

```powershell
pip install -r ferramentas/requirements.txt
python -m ferramentas.red_model_studio
```

## Base URL padrao

```text
http://redsystems.ddns.net/ollama
```

O app guarda a URL, modelo selecionado e configuracoes basicas em `QSettings`.

## Observacoes

- O app usa `/v1/chat/completions` com `stream_options.include_usage=true`, entao os tokens/s sao calculados em cima do uso real devolvido pelo proxy quando o modelo expuser `usage`.
- Na aba de imagens, os tamanhos foram limitados a resolucoes seguras para evitar erro de backend nos modelos NIM de imagem.
- O nome final do modelo exibido nas metricas vem da resposta real do proxy, nao so do dropdown.
