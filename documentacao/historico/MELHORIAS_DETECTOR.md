# MELHORIAS PARA O PROJECT_DETECTOR_V3

## Problemas Identificados

### 1. DRIVER - Backend dentro de frontend
- **Problema**: IA copia `backend/backend/server.mjs` (path errado)
- **Causa**: Detector não identifica que `apps/driver/backend/` é apenas para DEV
- **Solução**: Detectar backends locais em frontends e ignorá-los no Dockerfile

### 2. RONALD - Estrutura frontend/backend separadas
- **Problema**: IA tenta copiar `apps/ronald/dist` que não existe
- **Causa**: Ronald tem `frontend/` e `backend/` como subpastas, não é detectado corretamente
- **Solução**: Detectar estrutura de subpastas e decidir qual parte buildar

### 3. Falta de validação de paths
- **Problema**: Dockerfile tenta COPY de arquivos que não existem
- **Causa**: Nenhuma validação antes de gerar o COPY
- **Solução**: Validar que todos os paths no COPY existem

## Melhorias Necessárias

### A. Detector de Estrutura Avançado

Adicionar função que detecta padrões especiais:

```python
def _detect_project_structure(self, project_path: Path) -> dict:
    """
    Detecta estruturas especiais:
    - frontend/ + backend/ separados
    - backend/ dentro de frontend (dev only)
    - dist/ customizado (vite outDir)
    """
    structure = {
        "type": "simple",  # simple | split_frontend_backend | frontend_with_dev_backend
        "frontend_path": None,
        "backend_path": None,
        "dev_backend": False,
    }
    
    # Caso 1: frontend/ e backend/ como subpastas
    frontend_dir = project_path / "frontend"
    backend_dir = project_path / "backend"
    
    if frontend_dir.is_dir() and backend_dir.is_dir():
        # Verificar se ambos têm package.json ou equivalente
        has_frontend_pkg = (frontend_dir / "package.json").is_file()
        has_backend_pkg = (backend_dir / "package.json").is_file() or \
                          (backend_dir / "requirements.txt").is_file() or \
                          (backend_dir / "go.mod").is_file()
        
        if has_frontend_pkg and has_backend_pkg:
            structure["type"] = "split_frontend_backend"
            structure["frontend_path"] = "frontend"
            structure["backend_path"] = "backend"
            return structure
    
    # Caso 2: backend/ dentro de app frontend (dev only)
    backend_dir = project_path / "backend"
    if backend_dir.is_dir():
        # Verificar se é um backend de dev (tem server.mjs, db.json, etc)
        has_dev_files = (backend_dir / "server.mjs").is_file() or \
                        (backend_dir / "db.json").is_file()
        
        # Verificar se o app principal é frontend
        has_vite = any((project_path / f).is_file() for f in ["vite.config.ts", "vite.config.js"])
        
        if has_dev_files and has_vite:
            structure["type"] = "frontend_with_dev_backend"
            structure["dev_backend"] = True
            return structure
    
    return structure
```

### B. Prompt Melhorado para IA

Adicionar ao prompt instruções específicas:

```python
## ESTRUTURAS ESPECIAIS DETECTADAS:
{structure_info}

### Se type = "split_frontend_backend":
- O projeto tem frontend/ e backend/ SEPARADOS
- Você DEVE escolher qual parte deployar baseado no contexto
- Se for deploy de frontend: use apenas frontend/, ignore backend/
- Se for deploy de backend: use apenas backend/, ignore frontend/
- O build do frontend está em frontend/package.json
- O dist do frontend estará em frontend/dist (não apps/nome/dist)

### Se type = "frontend_with_dev_backend":
- O projeto é um FRONTEND com backend/ apenas para DEV
- NUNCA copie arquivos de backend/ no Dockerfile
- O backend/ NÃO vai para produção
- Use apenas os arquivos do frontend (src/, package.json, vite.config, etc)

### Se type = "simple":
- Estrutura normal, proceda normalmente
```

### C. Validador de Paths no Dockerfile

Adicionar validação antes de retornar:

```python
def _validate_dockerfile_paths(self, dockerfile: str, project_path: str) -> tuple[bool, list]:
    """
    Valida que todos os COPY no Dockerfile apontam para arquivos/pastas que existem.
    Retorna (is_valid, missing_paths)
    """
    import re
    
    missing = []
    copy_lines = re.findall(r'COPY\s+(?!--from=)([^\s]+)', dockerfile)
    
    for path in copy_lines:
        # Resolver path relativo ao root do repo
        if path.startswith('/app/'):
            path = path[5:]  # Remove /app/
        
        # Verificar se existe
        full_path = Path(project_path).parent / path  # parent = root do repo
        if not full_path.exists():
            missing.append(path)
    
    return len(missing) == 0, missing
```

### D. Sanitizador Melhorado

Melhorar o `_sanitize_dockerfile` para:

1. **Remover COPYs de backends dev**:
```python
# Detectar e remover COPY de backend/ em frontends
if 'backend/' in stripped and 'vite' in dockerfile.lower():
    logger.warning(f"Sanitize: removido COPY de backend dev: {stripped}")
    continue
```

2. **Corrigir paths de dist em estruturas split**:
```python
# Se estrutura é split_frontend_backend, ajustar paths
if structure["type"] == "split_frontend_backend":
    # /app/apps/ronald/dist -> /app/apps/ronald/frontend/dist
    result = result.replace(
        f'/app/{copy_path}/dist',
        f'/app/{copy_path}/frontend/dist'
    )
```

3. **Validar antes de retornar**:
```python
# Validar paths
is_valid, missing = self._validate_dockerfile_paths(result, project_path)
if not is_valid:
    logger.error(f"Dockerfile tem paths inválidos: {missing}")
    # Tentar corrigir automaticamente ou retornar None
```

### E. Fallback Local Melhorado

Atualizar `LocalFallbackDetector` para detectar estruturas split:

```python
def detect(self, scan_result: dict, app_name: str, base_port: int, copy_path: str = ".") -> dict:
    # ... código existente ...
    
    # NOVO: Detectar estrutura
    project_path = Path(scan_result.get("_project_path", "."))
    structure = self._detect_structure(project_path)
    
    if structure["type"] == "split_frontend_backend":
        # Decidir qual parte buildar
        # Por padrão, se tem frontend/, builda frontend
        if structure["frontend_path"]:
            return self._node_frontend_split(app_name, copy_path, structure, cfg)
        elif structure["backend_path"]:
            return self._backend_split(app_name, copy_path, structure, cfg)
```

## Implementação

Vou criar um arquivo `project_detector_v4.py` com todas essas melhorias implementadas.

### Principais Mudanças:

1. ✅ Detector de estrutura avançado
2. ✅ Prompt melhorado com instruções específicas
3. ✅ Validador de paths no Dockerfile
4. ✅ Sanitizador mais inteligente
5. ✅ Fallback local com suporte a estruturas split
6. ✅ Logs mais detalhados para debug

### Casos de Teste:

- **DRIVER**: Deve ignorar `backend/` e buildar apenas frontend
- **RONALD**: Deve detectar split e buildar `frontend/` corretamente
- **API**: Deve funcionar normalmente (backend puro)
- **ADMIN**: Deve funcionar normalmente (frontend puro)

### Compatibilidade:

- ✅ API pública mantida (`analyze_project`)
- ✅ Schema de retorno idêntico
- ✅ Webhook não precisa de mudanças
- ✅ Fallback continua funcionando se IA falhar
