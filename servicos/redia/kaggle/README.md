# REDIA Kaggle Image Worker

Worker para usar GPU do Kaggle como gerador de imagens da REDIA.

Este worker nao expoe porta publica. Ele faz pull de jobs na REDIA:

```text
Kaggle -> POST /api/image/worker/claim
Kaggle -> gera imagem
Kaggle -> POST /api/image/worker/result
```

## Variaveis No Kaggle

Configure no notebook:

```python
import os
os.environ["REDIA_BASE_URL"] = "http://redsystems2.ddns.net:3099"
os.environ["REDIA_WORKER_TOKEN"] = "COLE_O_MESMO_TOKEN_DO_REDIA_IMAGE_WORKER_TOKEN"
os.environ["REDIA_MODEL_ID"] = "stabilityai/sdxl-turbo"
```

## Celula De Instalacao

```python
!pip install -q --upgrade diffusers transformers accelerate safetensors pillow requests
```

## Rodar 1 Worker

```python
!python /kaggle/working/redia_kaggle_image_worker.py --worker-name kaggle-t4-0 --device cuda:0
```

## Rodar 2 Workers Em 2x T4

```python
!python /kaggle/working/redia_kaggle_image_worker.py --dual
```

Se o notebook nao estiver em `/kaggle/working`, envie este arquivo para la ou ajuste o caminho.

## Modelos Faceis

MVP rapido:

```text
stabilityai/sdxl-turbo
```

Depois podemos trocar para SDXL Lightning/checkpoint local, mantendo o mesmo protocolo de fila.
