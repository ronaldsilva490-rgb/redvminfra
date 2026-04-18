# RED SEB Debug Streamer

GUI simples em Python para publicar uma imagem local como se fosse uma frame de uma sessao SEB no monitor remoto.

Fluxo:

1. escolha uma `.jpg` ou `.png`;
2. informe a URL do monitor;
3. a ferramenta abre um WebSocket em `/seb-live`;
4. envie uma vez ou inicie o stream;
5. abra o painel do SEB e use o comite de IA em cima dessa sessao fake.

## Executar

```powershell
pip install -r ferramentas/requirements.txt
python -m ferramentas.seb_frame_streamer
```

## Campos principais

- `Base URL do SEB`: ex. `http://redsystems.ddns.net:2580`
- `Session ID`: nome da sessao fake
- `View ID`: id da view fake
- `Titulo` e `URL`: ajudam a identificar a sessao no painel
- `Intervalo (ms)`: frequencia do stream

## Canal usado

- `WS /seb-live`

O payload enviado segue a mesma estrutura que o monitor espera do navegador SEB: `sessionId`, `viewId`, `windowId`, `isMainWindow`, `title`, `url`, `width`, `height` e `imageBase64`.
