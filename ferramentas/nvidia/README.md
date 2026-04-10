# NVIDIA Tools

Utilitarios locais para catalogo e probes dos modelos NVIDIA NIM/NVCF.

## Probe de chat no catalogo vivo

Script:

```powershell
python ferramentas\nvidia\test_nim_catalog_chat.py --refresh-catalog
```

O script:

- busca a key NVIDIA do ambiente local ou, se preciso, da VM principal via SSH;
- baixa a lista viva atual de `https://integrate.api.nvidia.com/v1/models`;
- salva o catalogo em `artefatos/catalogos/nvidia/`;
- testa os modelos em ordem alfabetica usando uma pergunta simples;
- grava resultados detalhados em JSON/JSONL.

Artefatos relevantes:

- `artefatos/catalogos/nvidia/nvidia_nim_models_live.json`
- `artefatos/catalogos/nvidia/nvidia_nim_models_live.txt`
- `artefatos/catalogos/nvidia/nvidia_nim_chat_probe_results_latest.json`
- `artefatos/catalogos/nvidia/nvidia_nim_chat_ok_models_latest.txt`
