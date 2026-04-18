# RED SEB Debug Streamer

GUI simples em Python para publicar uma imagem local como se fosse uma frame de uma sessao SEB no monitor remoto.

Fluxo:

1. escolha uma `.jpg` ou `.png`;
2. informe a URL do monitor;
3. envie uma vez ou inicie o stream;
4. abra o painel do SEB e use o comite de IA em cima dessa sessao fake.

## Executar

```powershell
pip install -r ferramentas/requirements.txt
python -m ferramentas.seb_frame_streamer
```

## Campos principais

- `Base URL do SEB`: ex. `http://redsystems.ddns.net:2580`
- `Token debug`: token configurado no `RED_SEB_DEBUG_TOKEN` da VM
- `Session ID`: nome da sessao fake
- `View ID`: id da view fake
- `Titulo` e `URL`: ajudam a identificar a sessao no painel
- `Intervalo (ms)`: frequencia do stream

## Endpoints usados

- `POST /api/debug/fake-frame`
- `POST /api/debug/session/clear`

## Observacao

O endpoint de debug deve ficar protegido por token na VM. A GUI envia esse token no header `x-red-seb-debug-token`.
