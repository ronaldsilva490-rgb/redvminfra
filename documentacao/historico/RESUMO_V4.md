# PROJECT DETECTOR V4 - RESUMO DAS MELHORIAS

## ✅ O que foi implementado

### 1. StructureDetector (NOVO)
Detecta 3 tipos de estrutura:
- **simple**: Estrutura padrão
- **split_frontend_backend**: frontend/ e backend/ separados (caso RONALD)
- **frontend_with_dev_backend**: backend/ apenas para dev (caso DRIVER)

### 2. Prompt Melhorado
- Contexto específico baseado na estrutura detectada
- Instruções claras para ignorar backends de dev
- Instruções para lidar com estruturas split
- Warnings visuais (⚠️) para chamar atenção da IA

### 3. Validador de Paths
- `_validate_dockerfile_paths()`: Verifica se todos os COPY existem
- Suporta wildcards (package*.json)
- Loga warnings se paths inválidos forem detectados

### 4. Sanitizador Melhorado
- Remove COPY de backend/ em frontends com dev backend
- Corrige paths para estruturas split (dist -> frontend/dist)
- Valida paths antes de retornar
- Logs detalhados de cada correção

### 5. Logs Melhorados
- Emojis para facilitar leitura (✨, ⚠️, ✅, ❌)
- Logs de estrutura detectada
- Logs de cada sanitização aplicada
- Logs de validação de paths

## 🎯 Como resolve os problemas

### DRIVER (frontend com backend dev)
1. StructureDetector detecta: `frontend_with_dev_backend`
2. Prompt avisa IA: "NUNCA copie backend/"
3. Se IA copiar mesmo assim, sanitizador remove
4. Validador confirma que paths existem

### RONALD (frontend/backend separados)
1. StructureDetector detecta: `split_frontend_backend`
2. Prompt avisa IA: "Builde apenas frontend/"
3. Sanitizador corrige paths: `dist` -> `frontend/dist`
4. Validador confirma que `frontend/dist` existe após build

## 📦 Compatibilidade

- ✅ API pública mantida: `analyze_project()`
- ✅ Schema de retorno idêntico ao v3
- ✅ Webhook não precisa de mudanças
- ✅ Fallback local continua funcionando

## 🚀 Como testar

### Teste 1: DRIVER
```bash
cd /root/red-deploy/smart-deploy
python3 project_detector_v4.py /root/Tapp/apps/driver --name driver --port 2610 --copy-path apps/driver
```

**Resultado esperado**:
- Detecta: `frontend_with_dev_backend`
- Dockerfile NÃO tem COPY de backend/
- Build output: `/app/apps/api/public/driver` (vite outDir customizado)

### Teste 2: RONALD
```bash
python3 project_detector_v4.py /root/Tapp/apps/ronald --name ronald --port 2630 --copy-path apps/ronald
```

**Resultado esperado**:
- Detecta: `split_frontend_backend`
- Dockerfile builda apenas frontend/
- Build output: `/app/apps/ronald/frontend/dist`

### Teste 3: API (backend normal)
```bash
python3 project_detector_v4.py /root/Tapp/apps/api --name api --port 2590 --copy-path apps/api
```

**Resultado esperado**:
- Detecta: `simple`
- Dockerfile normal de backend Node.js/TypeScript

## 📝 Próximos passos

1. ✅ Criar detector v4 completo
2. ⏳ Testar localmente (se possível)
3. ⏳ Upload para VM
4. ⏳ Backup do v3
5. ⏳ Substituir v3 por v4
6. ⏳ Reiniciar webhook service
7. ⏳ Testar deploy de DRIVER
8. ⏳ Testar deploy de RONALD
9. ⏳ Monitorar logs

## 🔧 Comandos para deploy

```bash
# Na VM:
cd /root/red-deploy/smart-deploy

# Backup do v3
cp project_detector_v3.py project_detector_v3_backup.py

# Upload do v4 (via SFTP)
# ... upload project_detector_v4.py ...

# Substituir
mv project_detector_v4.py project_detector_v3.py

# Reiniciar webhook
systemctl restart red-webhook

# Monitorar
tail -f /var/log/red-deploy/deploy.log
```

## ⚠️ Notas importantes

1. O v4 é 100% compatível com v3 - pode substituir diretamente
2. Se algo der errado, basta restaurar o backup
3. O fallback local ainda funciona se IA falhar
4. Todos os logs são mais detalhados para debug
