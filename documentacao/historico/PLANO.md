# PLANO.md — Bugs, Correcoes Pendentes e Proximos Passos

## STATUS ATUAL (2026-04-03)

### O que funciona:
- Webhook v3 recebe pushes do GitHub e processa corretamente
- Detector v3 analisa projetos com IA (qwen3-coder-next via proxy)
- Fallback local funciona quando IA esta offline
- Auto-discovery de apps novas em apps/ (aloca portas automaticamente)
- Limpeza automatica quando uma app e removida do repo
- Rollback automatico se health check falhar
- Dashboard web (porta 8888)
- PostgreSQL cria databases automaticamente por app
- Proxy Ollama funciona com pool de keys

### O que NAO funciona ainda:
- Nenhum container de app esta rodando (apps ainda sao esbocos)
- As apps nao tem conteudo concreto — devs ainda vao alimentar

---

## BUGS CONHECIDOS

### BUG 1: Frontends tem outDir customizado no Vite
- **Problema**: admin, driver e restaurant tem `outDir: '../api/public/NOME'` no vite.config
- **Efeito**: O build output nao fica em `apps/NOME/dist/`, fica em `apps/api/public/NOME/`
- **Status**: Sanitizador corrigido para detectar e ajustar o path automaticamente
- **Teste**: driver, admin, restaurant buildaram com sucesso (docker build OK)
- **Acao**: Nenhuma. Ja funciona. Quando os devs pusharem codigo real, vai buildar certo.

### BUG 2: @tapp/ui nao listava @tapp/config como dependencia
- **Problema**: packages/ui/tsconfig.json extende @tapp/config/tsconfig.react.json mas nao listava como dep
- **Efeito**: `turbo build` falhava com "File '@tapp/config/tsconfig.react.json' not found"
- **Status**: CORRIGIDO. Commitado na VM: `fix(ui): add missing @tapp/config devDependency`
- **Acao**: Fazer `git push` da VM para o GitHub (ou puxar o commit localmente)

### BUG 3: API backend nao builda com tsc puro
- **Problema**: `apps/api` usa `rootDir: "src"` no tsconfig, mas importa `@tapp/shared` que esta fora
- **Efeito**: `tsc` reclama que arquivos de shared nao estao sob rootDir
- **Status**: NAO CORRIGIDO. E um problema do projeto, nao do sistema de deploy.
- **Possivel fix no projeto**:
  1. Trocar o build command de `tsc` para `tsup` ou `esbuild` (bundlers que ignoram rootDir)
  2. Ou usar `tsc --project tsconfig.build.json` com um tsconfig sem rootDir
  3. Ou remover `rootDir` do tsconfig da api e ajustar os imports
- **Acao**: O dev responsavel pela API precisa ajustar o build. O deploy system vai funcionar assim que o build local funcionar.

### BUG 4: IA as vezes retorna campos com nomes diferentes
- **Problema**: Modelo retorna `dockerfile_content` em vez de `dockerfile`, ou `project_name` em vez de `project_type`
- **Status**: CORRIGIDO. Adicionado normalizador de nomes de campos no validator.

### BUG 5: IA retorna JSON com markdown wrapping
- **Problema**: Resposta vem como ```json { ... } ``` em vez de JSON puro
- **Status**: CORRIGIDO. Adicionado strip de markdown antes do parse.

### BUG 6: Turbo filter com path em vez de package name
- **Problema**: IA gera `--filter=apps/driver` mas turbo espera `--filter=@tapp/driver`
- **Status**: CORRIGIDO. Sanitizador le o package.json do app e corrige o filter.

---

## CORRECOES APLICADAS AO project_detector_v3.py

1. Removido enums rigidos do JSON schema (confundia o modelo)
2. Schema reduzido — so `required` os campos essenciais
3. Adicionado `_strip_markdown()` para limpar resposta da IA
4. Adicionado `_normalize_field_names()` para aceitar nomes alternativos
5. Adicionado `_infer_from_dockerfile()` para preencher campos ausentes
6. Adicionado `_normalize_enum()` para mapear valores fora do enum ("Vite React" -> "frontend")
7. Adicionado `_sanitize_dockerfile()`:
   - Corrige turbo filter (path -> package name)
   - Corrige COPY de arquivos inexistentes (nginx.conf, .env)
   - Detecta outDir real do vite.config e ajusta COPY path
   - Adiciona nginx config inline se ausente
   - Injeta package.json em stages multi-stage que precisam
8. Duas tentativas de IA: 1a com format schema, 2a sem (mais flexivel)
9. System prompt explicito pedindo nomes exatos dos campos
10. Prompt com instrucoes detalhadas sobre monorepo, turbo, nginx, portas

---

## PROXIMOS PASSOS

### Prioridade ALTA (precisa antes dos devs pusharem)
- [ ] Fazer `git push` do commit `fix(ui)` da VM para o GitHub
- [ ] Verificar que o webhook esta realmente ativo e respondendo (testar com curl)
- [ ] Garantir que UFW tem as portas dos apps abertas (2580-2630)

### Prioridade MEDIA (melhorias)
- [ ] Resolver o build da API (bug 3) — precisa do dev ajustar tsconfig ou trocar para bundler
- [ ] Adicionar nginx config para apps com `base` path (ex: `/driver/`, `/admin/`)
- [ ] Implementar limpeza de imagens Docker antigas (para nao encher disco)
- [ ] Adicionar notificacao (Slack/Discord) quando deploy falha

### Prioridade BAIXA (nice to have)
- [ ] Melhorar o dashboard com logs em tempo real
- [ ] Adicionar metricas de uso de recursos por container
- [ ] Implementar deploy por branch (nao so main)
- [ ] Adicionar suporte a docker-compose para apps que precisam de multiplos containers

---

## COMO TESTAR O SISTEMA

### Teste rapido do webhook (de dentro da VM):
```bash
curl -s http://localhost:9000/health
# Deve retornar: {"status":"ok","service":"Red Deploy Webhook v3","version":"3.0.0"}
```

### Teste do detector de projetos:
```bash
cd /root/red-deploy/smart-deploy
python3 project_detector_v3.py /root/Tapp/apps/driver --name driver --port 2610 --copy-path apps/driver
```

### Teste do proxy IA:
```bash
# De dentro da VM (curl nao instalado, usar python):
python3 -c "import requests; r=requests.get('http://localhost:8080/api/tags'); print(r.status_code, r.text[:200])"
```

### Teste de build Docker:
```bash
cd /root/red-deploy/smart-deploy
python3 project_detector_v3.py /root/Tapp/apps/NOME --name NOME --port PORTA --copy-path apps/NOME
# Salvar o Dockerfile gerado e rodar:
cd /root/Tapp && docker build -f Dockerfile.NOME -t test-NOME .
```
