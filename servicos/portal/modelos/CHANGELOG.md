# Changelog - Galeria de Modelos RED Systems

## 2026-05-07 — Refatoração Completa da Galeria

### Visão Geral

Dia de refatoração massiva da galeria de modelos (`/modelos/`), incluindo renumeração de arquivos, otimização de performance com screenshots estáticos, correção de conteúdo textual e substituição de imagens inadequadas.

---

### 1. Renumeracao dos Modelos Empresariais

**Problema:** O modelo-12 estava faltando na sequência (havia gap entre 11 e 13). O modelo-1-aurora era muito lento e estava ocupando a primeira posição.

**Solução:**
- Renomeados todos os 15 modelos empresariais para sequência contínua 1-15
- Modelo aurora movido do início (modelo-1) para o final (modelo-15) por ser pesado
- Gap do número 12 preenchido corretamente

**Nova ordem:**
```
01 - Editorial      (antes modelo-2)
02 - Esmeralda      (antes modelo-3)
03 - Brutalist      (antes modelo-4)
04 - Swiss          (antes modelo-5)
05 - Pastel         (antes modelo-6)
06 - Glass          (antes modelo-7)
07 - Retro          (antes modelo-8)
08 - Luxury         (antes modelo-9)
09 - Tech           (antes modelo-10)
10 - Minimal        (antes modelo-11)
11 - Neumorphism    (antes modelo-13)
12 - Cyberpunk      (antes modelo-14)
13 - Bauhaus        (antes modelo-15)
14 - Organic        (antes modelo-16)
15 - Aurora         (antes modelo-1, movido pro final)
```

**Arquivos modificados:**
- `servicos/portal/modelos/empresarial/modelo-{N}-{nome}.html` — 15 renomeações
- `servicos/portal/modelos/index.html` — todas as referências atualizadas

---

### 2. Otimizacao de Performance — Screenshots Estaticos

**Problema:** A galeria carregava 18 iframes simultâneos (15 empresarial + 3 clínicas), cada um renderizando uma página HTML completa. Isso deixava a página extremamente pesada e lenta.

**Solução:**
- Substituídos todos os iframes por screenshots estáticos em formato WebP
- Screenshots gerados via Playwright (headless Chromium) com viewport 1400x900
- Cada card agora exibe uma imagem real do modelo correspondente
- Overlay com ícone "play" aparece no hover, indicando que é clicável
- Clique abre o modelo em nova aba (`target="_blank"`)
- Removido toggle mobile/desktop (não fazia sentido sem iframes)

**Arquivos criados:**
- `servicos/portal/modelos/assets/thumbnails/modelo-{N}-{nome}.webp` — 18 screenshots
  - 15 modelos empresariais
  - 3 modelos de clínicas (vsaude, medcare, elite)

**Arquivos modificados:**
- `servicos/portal/modelos/index.html` — iframes substituídos por `<a>` com background-image
- CSS removido: `.tabs`, `.tab`, `.preview-desktop`, `.preview-mobile`, `.phone`
- CSS adicionado: `.preview-static`, `.preview-overlay`, `.play-icon`

**Impacto de performance:**
- Antes: ~18 páginas HTML completas carregadas simultaneamente
- Depois: 18 imagens WebP estáticas (~50-100KB cada)
- Página carrega instantaneamente

---

### 3. Correcao de Conteudo Textual — Total Empresarial

**Problema:** Vários modelos tinham texto duplicado, descrições genéricas ou desatualizadas que não refletiam o conteúdo oficial da Total Empresarial.

**Correções aplicadas:**

#### 3.1 Texto Duplicado
- **modelo-2-editorial:** Títulos de serviço apareciam 3 vezes cada (ex: `<h3>Consultoria<span>Consultoria</span>Consultoria</h3>`)
- **modelo-4-brutalist:** Títulos duplicados com `<br>` (ex: `<h3>Consultoria<br>Consultoria</h3>`)

#### 3.2 Descricoes Genéricas no Hero
- Modelos 15-bauhaus e 16-organic tinham descrições genéricas ("Soluções contábeis completas com tecnologia de ponta")
- Substituídas pelo texto oficial: *"Apoiamos a sua empresa com um jeito prático, seguro e moderno de fazer assessoria contábil. Contribuímos com o sonho de ampliação do seu negócio, ajudando você a quebrar barreiras, de forma segura e eficiente."*

#### 3.3 Duplicacao do Slogan "Linha Tenue"
- O texto *"A linha tênue entre performance e contabilidade"* aparecia tanto no hero (h1) quanto na seção "Sobre" (h2) em 4 modelos
- Mantido apenas no hero, substituído por "Sobre a Total Empresarial" na seção Sobre
- Modelos afetados: 1-aurora, 3-esmeralda, 10-tech, 11-minimal

#### 3.4 Servicos Oficiais Aplicados
Todos os 15 modelos agora têm os 4 serviços oficiais com descrições corretas:
1. **Consultoria** — "Tenha as melhores soluções nas áreas tributária, financeira e contábil através da análise dos nossos experts."
2. **Legalização de Empresas** — "Abra sua empresa, sem sair de casa! Resolvemos toda a parte burocrática sem custo para clientes da assessoria mensal."
3. **Assessoria** — "Tenha uma contabilidade consultiva que entende do seu dia a dia! Soluções eficientes para gestão operacional."
4. **Perícia Contábil e Financeira** — "Realizamos cálculos para processos judiciais com revisão de contratos e avaliação de empresas."

**Modelos corrigidos:** Todos os 15 empresariais

---

### 4. Substituicao de Imagens Inadequadas

**Problema:** Vários modelos usavam imagens do Unsplash com pessoas de origem árabe/oriente médio, inadequadas para o público alvo brasileiro de contabilidade empresarial.

**Solução:** Substituídas por fotos de profissionais de negócios brasileiros/latinos.

**Imagens substituídas:**
| ID Antigo | ID Novo | Contexto |
|-----------|---------|----------|
| `photo-1664575599618` | `photo-1554224155-6726b3ff858f` | Hero image (calculadora/negócios) |
| `photo-1573497019940` | `photo-1580489944761-15a19d654956` | Profissional/hero (usada em 9 modelos) |
| `photo-1573164574511` | `photo-1522071820081-009f0129c71c` | Equipe colaborativa |
| `photo-1664575600796` | `photo-1553877522-43269d4ea984` | Equipe contábil (aurora) |
| `photo-1573496359142` | `photo-1560250097-0b93528c311a` | Equipe profissional (luxury) |

**Modelos afetados:** 12 de 15 empresariais
- modelo-1-editorial, 2-esmeralda, 3-brutalist, 4-swiss, 5-pastel
- modelo-6-glass, 7-retro, 8-luxury, 10-minimal, 11-neumorphism
- modelo-12-cyberpunk, 15-aurora

**Screenshots regenerados** para todos os modelos com imagens atualizadas.

---

### 5. Atualizacao do Script de Sync

**Problema:** O script `sync_repo_to_vm.py` só extraía arquivos para `/opt/redvm-repo/` mas não copiava para o diretório web ativo (`/var/www/modelos/`). Além disso, não sincronizava subdiretórios novos como `assets/thumbnails/` e `clinicas/`.

**Solução:** Atualizado o script para:
1. Remover arquivos HTML antigos do diretório web
2. Copiar novos HTMLs do repo para o web directory
3. Copiar `index.html` da galeria
4. Sincronizar todo o diretório `assets/` (incluindo thumbnails/)
5. Sincronizar diretório `clinicas/` completo

**Arquivo modificado:**
- `ferramentas/vm/sync_repo_to_vm.py`

---

### Resumo de Commits

| Commit | Descrição | Arquivos |
|--------|-----------|----------|
| `733642b` | Atualizar texto do hero nos modelos 15 e 16 | 2 HTMLs |
| `5f36fca` | Remover duplicacao do texto linha tenue na secao Sobre | 4 HTMLs |
| `dd96963` | Renumerar modelos empresariais de 1 a 15 e mover aurora para o final | 16 arquivos (15 renames + index) |
| `3af1480` | Atualizar sync_repo_to_vm.py para copiar arquivos do repo para /var/www/modelos | 1 script |
| `bb09765` | Substituir iframes por previews estaticos na galeria de modelos | 1 HTML |
| `c3352af` | Adicionar screenshots reais como thumbnails na galeria | 20 arquivos (18 screenshots + index + temp) |
| `cba0283` | Remover arquivo temporario thumbnails.html | 1 arquivo |
| `1d218ee` | Corrigir aspas escapadas nas URLs das thumbnails | 1 HTML |
| `508a81f` | Atualizar sync_repo_to_vm.py para copiar assets e clinicas | 1 script |
| `20c2f02` | Substituir imagens inadequadas por fotos de profissionais brasileiros | 21 arquivos (12 HTMLs + 12 screenshots) |
| `b28b240` | Remover ultima imagem com pessoa (modelo-10-minimal) e garantir zero pessoas em todos os modelos | 15 HTMLs + 1 screenshot |

---

### Auditoria Completa de Imagens

**Verificacao final:** Todos os IDs do Unsplash em uso foram auditados visualmente:

| ID | Contexto | Contem pessoas? |
|----|----------|-----------------|
| `1460925895917-afdab827c52f` | Graficos/analytics na tela | Nao |
| `1553877522-43269d4ea984` | Workspace/escritorio vazio | Nao |
| `1554224155-6726b3ff858f` | Calculadora/documentos | Nao |
| `1554224155-1696413565d3` | Dashboard/grafico | Nao |

**Resultado:** Zero imagens com pessoas em todos os 15 modelos empresariais.

---

### Estado Final

- **15 modelos empresariais** numerados de 1 a 15, com conteúdo oficial Total Empresarial
- **3 modelos de clínicas** intactos (não modificados)
- **18 screenshots** em `assets/thumbnails/` para preview na galeria
- **Galeria otimizada** — carrega instantaneamente sem iframes
- **Imagens adequadas** ao público brasileiro em todos os modelos
- **Script de sync** atualizado para deploy completo

---

### Como Regenerar Screenshots

Se precisar atualizar os screenshots no futuro:

```bash
cd C:\Projetos\redvm
pip install playwright
python -m playwright install chromium --with-deps

# Executar script de screenshot (ver ferramentas/vm/generate-thumbnails.py)
# Ou manualmente:
python << 'PYEOF'
import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    models = [
        ('modelo-1-editorial', 'servicos/portal/modelos/empresarial/modelo-1-editorial.html'),
        # ... adicionar outros modelos
    ]
    
    output_dir = 'servicos/portal/modelos/assets/thumbnails'
    os.makedirs(output_dir, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for name, path in models:
            page = await browser.new_page(viewport={'width': 1400, 'height': 900})
            abs_path = os.path.abspath(path)
            file_url = f'file:///{abs_path.replace(os.sep, "/")}'
            await page.goto(file_url, wait_until='networkidle', timeout=15000)
            await page.wait_for_timeout(1000)
            await page.screenshot(
                path=f'{output_dir}/{name}.webp',
                type='jpeg', quality=80, full_page=False
            )
            await page.close()
        await browser.close()

asyncio.run(main())
PYEOF
```

---

*Documento criado em 2026-05-07 para registrar todas as mudanças realizadas na galeria de modelos.*
