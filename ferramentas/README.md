# Ferramentas

Ferramentas locais reaproveitaveis:

```text
vm/           Conexao Paramiko/env.
implantacao/  Analisadores e helpers de deploy.
diagnosticos/ Espaco para checks sem credenciais hardcoded.
avaliacoes/   Benchmarks de modelos.
nvidia/       Testes e utilitarios NVIDIA NIM/NVCF.
red_model_studio/ App desktop PySide6 para testar chat/imagem do proxy.
```

Scripts antigos com senha hardcoded foram preservados em `.privado/legacy-vm-scripts/` e nao devem ser publicados.

## RED Model Studio

Ferramenta desktop local para conversar com os modelos do proxy RED e testar geracao de imagens.

Executar:

```powershell
pip install -r ferramentas/requirements.txt
python -m ferramentas.red_model_studio
```
