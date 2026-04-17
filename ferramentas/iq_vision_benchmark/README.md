# IQ Vision Benchmark

Ferramenta curta para testar os modelos **vision** do proxy RED em cima do
ultimo frame salvo pelo `iq-bridge`.

## Como usar

1. recarregue a extensao `RED IQ Demo Vision`
2. troque de ativo na IQ para forcar um frame novo
3. rode:

```powershell
python ferramentas/iq_vision_benchmark/benchmark_latest_frame.py
```

## O que ela mede

- latencia por modelo
- campos lidos da tela:
  - ativo
  - mercado
  - payout
  - countdown
  - investimento
  - expiracao
  - labels dos botoes

Os resultados ficam em:

```text
artefatos/iq_vision_benchmark/
```
