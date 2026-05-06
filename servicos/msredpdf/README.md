# MS RED PDF

Backend e interface para analise assistida de documentos juridicos em PDF/DOCX usando o proxy IA da RED Systems.

## Publicacao

- rota publica: `/msredpdf/`
- runtime oficial: `/opt/msredpdf`
- dados de runtime: `/var/lib/msredpdf`
- servico systemd: `msredpdf.service`
- porta interna: `127.0.0.1:3142`
- estado em 2026-05-06: ativo na VM principal

## Fluxo

1. Cliente envia um PDF ou DOCX pela interface.
2. O backend salva o arquivo em `/var/lib/msredpdf/uploads`.
3. O texto e extraido por pagina no PDF ou por blocos no DOCX.
4. Se o PDF estiver escaneado ou com paginas sem texto, o backend aplica OCR com Tesseract (`por+eng`) antes da analise.
5. O backend decide a estrategia:
   - documento curto: analise consolidada em uma chamada;
   - documento longo: analise por pagina/bloco e consolidacao final.
6. O progresso real e enviado por SSE em `/api/jobs/{id}/events`.
7. O texto do relatorio tambem chega em streaming por eventos `report-delta`, para o cliente assistir a analise sendo escrita.
8. O resultado final e um relatorio juridico em Markdown, salvo no historico e disponivel em `/api/jobs/{id}`.

## Escopo da analise

O relatorio gerado cobre o escopo da proposta:

- leitura de contratos em PDF e DOCX;
- resumo automatico;
- sugestoes de clausulas e redacoes alternativas;
- identificacao e classificacao de riscos;
- historico da analise;
- pontos de LGPD e privacidade.

## Modelos e proxy

O padrao usa `mistral-large-latest`, com possibilidade de troca pela interface. O backend chama o proxy OpenAI-compatible em:

```text
MSREDPDF_PROXY_BASE_URL=http://127.0.0.1:8080/v1
```

Se a analise juridica for migrada para o RED Proxy Pro/Vercel AI Gateway, use:

```text
MSREDPDF_PROXY_BASE_URL=http://127.0.0.1:8095/v1
MSREDPDF_PROXY_API_KEY=red
MSREDPDF_MODEL=anthropic/claude-sonnet-4.6
MSREDPDF_REVIEW_MODEL=openai/gpt-5.5
```

Nao grave chaves reais no repo.

## LGPD

Por padrao `MSREDPDF_REDACT_BEFORE_AI=1`, entao e-mails, CPFs, CNPJs e telefones sao mascarados antes de enviar texto ao modelo. O PDF original permanece local na VM.

## Historico

Cada analise finalizada grava um JSON em `/var/lib/msredpdf/results`. A interface lista os ultimos resultados pelo endpoint:

```text
GET /api/history
```

## Instalacao em VM

```bash
apt install -y tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
mkdir -p /opt/msredpdf /var/lib/msredpdf
rsync -a servicos/msredpdf/ /opt/msredpdf/
python3 -m venv /opt/msredpdf/.venv
/opt/msredpdf/.venv/bin/pip install -r /opt/msredpdf/requirements.txt
cp servicos/msredpdf/.env.example /etc/msredpdf.env
cp infraestrutura/systemd/msredpdf.service /etc/systemd/system/msredpdf.service
systemctl daemon-reload
systemctl enable --now msredpdf
```

## Verificacao

```bash
curl http://127.0.0.1:3142/healthz
curl http://127.0.0.1/msredpdf/
systemctl status msredpdf --no-pager
```
