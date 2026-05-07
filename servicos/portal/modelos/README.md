# Galeria de Modelos - Total Empresarial

Colecao de 8 landing pages estaticas para demonstracao de templates empresariais.

## Estrutura

```text
modelos/
  index.html                  - Grid principal com os 8 modelos
  modelo-1-aurora.html        - Template Aurora (gradientes suaves)
  modelo-2-editorial.html     - Template Editorial (tipografia classica)
  modelo-3-esmeralda.html     - Template Esmeralda (verde elegante)
  modelo-4-brutalist.html     - Template Brutalist (design brutalista)
  modelo-5-swiss.html         - Template Swiss (minimalismo suico)
  modelo-6-pastel.html        - Template Pastel (cores suaves)
  modelo-7-glass.html         - Template Glass (efeito glassmorphism)
  modelo-8-retro.html         - Template Retro (estilo vintage)
  assets/
    logo.webp                 - Logo principal RED Systems
    logo-icon.webp            - Icone RED Systems
```

## Rotas nginx

Publicado em `/modelos/` via nginx:

```nginx
location = /modelos {
    return 301 /modelos/;
}

location /modelos/ {
    alias /var/www/modelos/;
    index index.html;
    try_files $uri $uri/ /modelos/index.html;
}
```

## Deploy na VM

Os arquivos devem ser copiados para `/var/www/modelos/` na VM:

```bash
# Via tarball
tar -czf modelos.tar.gz -C servicos/portal modelos/
# Upload e extracao na VM
tar -xzf modelos.tar.gz -C /var/www/ --overwrite
```

## Caracteristicas dos Modelos

### Modelo 1 - Aurora
Gradientes suaves em tons de azul/roxo, design moderno com animacoes sutis.

### Modelo 2 - Editorial
Tipografia classica serifada, layout inspirado em revistas impressas.

### Modelo 3 - Esmeralda
Paleta verde esmeralda, elegancia corporativa com elementos organicos.

### Modelo 4 - Brutalist
Design brutalista com bordas grossas, tipografia bold, contraste alto.

### Modelo 5 - Swiss
Minimalismo suico, grid rigoroso, tipografia Helvetica-style.

### Modelo 6 - Pastel
Cores suaves e acolhedoras, design amigavel e acessivel.

### Modelo 7 - Glass
Efeito glassmorphism com blur, transparencias, modernidade.

### Modelo 8 - Retro
Estilo vintage anos 80/90, cores vibrantes, nostalgia.

## Tecnologias

- HTML5 semantico
- CSS custom properties (variaveis)
- Google Fonts (Inter, JetBrains Mono, etc.)
- Design responsivo (mobile-first)
- Sem JavaScript necessario (puramente estatico)

## Historico

Deploy original: 2026-05-07
Commit: `62a1278` - "Deploy: galeria de 8 mockups Total Empresarial em /modelos/"
