# INSTRUÇÕES DE DEPLOY - DETECTOR V4

## 📋 O que foi feito

Criei o **Project Detector V4** com melhorias significativas sobre o V3:

### Principais Melhorias

1. **StructureDetector** - Detecta 3 tipos de estrutura:
   - `simple`: Estrutura padrão
   - `split_frontend_backend`: frontend/ e backend/ separados (RONALD)
   - `frontend_with_dev_backend`: backend/ apenas para dev (DRIVER)

2. **Prompt Melhorado** - Instruções específicas para cada estrutura

3. **Validador de Paths** - Verifica se todos os COPY existem antes de retornar

4. **Sanitizador Inteligente** - Remove COPYs inválidos automaticamente

5. **Logs Detalhados** - Emojis e mensagens claras para debug

## 🎯 Problemas Resolvidos

### DRIVER
- ❌ Antes: Copiava `backend/backend/server.mjs` (path errado)
- ✅ Agora: Detecta que backend/ é dev-only e ignora completamente

### RONALD
- ❌ Antes: Tentava copiar `apps/ronald/dist` (não existe)
- ✅ Agora: Detecta estrutura split e usa `apps/ronald/frontend/dist`

## 🚀 Como fazer o deploy

### Opção 1: Deploy Automático (Recomendado)

```bash
python redvm/deploy_v4.py
```

Este script vai:
1. Conectar na VM
2. Fazer backup do v3
3. Upload do v4
4. Perguntar confirmação
5. Substituir v3 por v4
6. Reiniciar webhook
7. Verificar status

### Opção 2: Deploy Manual

```bash
# 1. Conectar na VM
ssh root@redsystems.ddns.net -p 2222

# 2. Backup do v3
cd /root/red-deploy/smart-deploy
cp project_detector_v3.py project_detector_v3_backup_$(date +%Y%m%d_%H%M%S).py

# 3. Upload do v4 (via SFTP ou copiar conteúdo)
# ... upload project_detector_v4.py ...

# 4. Substituir
mv project_detector_v4.py project_detector_v3.py

# 5. Reiniciar webhook
systemctl restart red-webhook

# 6. Verificar
systemctl status red-webhook
```

## 🧪 Como testar

### Teste 1: DRIVER (frontend com backend dev)

```bash
# Na VM:
cd /root/red-deploy/smart-deploy
python3 project_detector_v3.py /root/Tapp/apps/driver --name driver --port 2610 --copy-path apps/driver
```

**Verificar**:
- Log mostra: "Estrutura detectada: Frontend com backend DEV"
- Dockerfile NÃO tem COPY de backend/
- Dockerfile usa `/app/apps/api/public/driver` (vite outDir)

### Teste 2: RONALD (frontend/backend separados)

```bash
python3 project_detector_v3.py /root/Tapp/apps/ronald --name ronald --port 2630 --copy-path apps/ronald
```

**Verificar**:
- Log mostra: "Estrutura detectada: SPLIT frontend/backend"
- Dockerfile builda apenas frontend/
- Dockerfile usa `/app/apps/ronald/frontend/dist`

### Teste 3: Deploy Real

```bash
# Trigger deploy manual via webhook
curl -X POST http://localhost:9000/deploy/driver
curl -X POST http://localhost:9000/deploy/ronald

# Monitorar logs
tail -f /var/log/red-deploy/deploy.log
```

## 📊 Monitoramento

### Logs para acompanhar

```bash
# Deploy log (principal)
tail -f /var/log/red-deploy/deploy.log

# Webhook log
tail -f /var/log/red-deploy/webhook.log

# Status do webhook
systemctl status red-webhook

# Containers rodando
docker ps -a
```

### O que procurar nos logs

✅ **Sucesso**:
```
✨ Estrutura detectada: frontend_with_dev_backend
Sanitize: removido COPY de backend dev: COPY backend/...
✅ Validação OK: type=frontend, lang=typescript, runtime=nginx, port=80
Build OK: driver-app
Health check OK: http://localhost:2610/
```

❌ **Problema**:
```
⚠️  Dockerfile tem paths inválidos: ['backend/backend/server.mjs']
ERROR: failed to build: "/backend/backend/server.mjs": not found
```

## 🔄 Rollback (se necessário)

Se algo der errado:

```bash
# Na VM:
cd /root/red-deploy/smart-deploy

# Restaurar backup
mv project_detector_v3_backup_TIMESTAMP.py project_detector_v3.py

# Reiniciar
systemctl restart red-webhook

# Verificar
systemctl status red-webhook
```

## ✅ Checklist de Deploy

- [ ] Backup do v3 criado
- [ ] V4 testado localmente (se possível)
- [ ] Upload do v4 para VM
- [ ] Substituição do v3 por v4
- [ ] Webhook reiniciado
- [ ] Status do webhook verificado (active/running)
- [ ] Teste manual do DRIVER
- [ ] Teste manual do RONALD
- [ ] Logs monitorados por 10 minutos
- [ ] Containers rodando corretamente

## 📞 Suporte

Se encontrar problemas:

1. Verificar logs: `/var/log/red-deploy/deploy.log`
2. Verificar webhook: `systemctl status red-webhook`
3. Restaurar backup se necessário
4. Reportar erro com logs completos

## 🎉 Resultado Esperado

Após o deploy bem-sucedido:

- ✅ DRIVER builda sem erros
- ✅ RONALD builda sem erros
- ✅ Containers rodando nas portas corretas
- ✅ Health checks passando
- ✅ Logs limpos sem erros de paths
