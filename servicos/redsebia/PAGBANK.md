# Guia de integração do PagBank no REDSEBIA

Este guia explica como ligar o `PagBank PIX` no REDSEBIA usando o painel administrativo já publicado.

Ele foi escrito em cima do que o serviço faz hoje:

- cria pedido PIX via `POST /orders`;
- usa token Bearer do PagBank;
- gera QR Code e código copia-e-cola;
- envia `notification_urls` automaticamente para o webhook do REDSEBIA;
- consulta status do pedido pelo `GET /orders/{id}`.

## O que você precisa antes

Antes de mexer no REDSEBIA, confirme estes pontos na sua conta PagBank:

1. você tem acesso ao **Portal do Desenvolvedor**;
2. você tem um **token** do ambiente certo;
3. sua conta possui **pelo menos uma chave PIX ativa**;
4. o `REDSEBIA_PUBLIC_BASE_URL` da VM está correto e público.

Sem chave PIX ativa na conta, o PagBank não gera o QR PIX do pedido.

## Onde pegar o token

### Sandbox

No ambiente de testes, pegue o token em:

1. Portal do Desenvolvedor;
2. aba **Tokens**;
3. copie o token sandbox.

### Produção

No ambiente real, pegue o token em:

1. desktop do PagBank;
2. menu lateral **Venda online**;
3. **Integrações**;
4. **Gerar Token**.

Importante: para o fluxo atual do REDSEBIA, o que usamos é o **token Bearer**.  
Hoje a integração implementada aqui **não depende** de `client_id` e `client_secret`.

## Campos do painel admin

No REDSEBIA, abra:

```text
/redsebia/admin
```

Entre em **Métodos de pagamento** e localize **PagBank PIX**.

Os campos que você vai ver são:

- `Ambiente`
- `Token`
- `CPF padrão (fallback)`
- `DDD (opcional)`
- `Telefone (opcional)`

### O que preencher em cada um

#### Ambiente

Use:

- `sandbox` para testes
- `production` para operação real

O token precisa combinar com o ambiente.  
Se você usar token de sandbox em `production`, ou o contrário, a API volta `401` / `Invalid credential`.

#### Token

Cole o token completo do PagBank, sem aspas e sem espaços extras.

#### CPF padrão (fallback)

O REDSEBIA envia um `customer.tax_id` na criação do pedido.

Hoje a lógica é:

- se o cliente do REDSEBIA tiver CPF cadastrado, usamos o CPF dele;
- se não tiver, usamos o `CPF padrão (fallback)` configurado no PagBank PIX.

Recomendação:

- para operação séria, capture o CPF real do cliente;
- para smoke test, o fallback ajuda a não travar a emissão.

#### DDD e Telefone

São opcionais, mas podem ajudar a manter o objeto `customer` mais completo.

Preencha só com números:

- `DDD`: `11`
- `Telefone`: `999999999`

Se deixar vazio, o REDSEBIA não envia `phones`.

## O que o REDSEBIA manda para o PagBank

Quando o cliente gera cobrança no portal, o backend monta um pedido com:

- `reference_id`
- `customer`
- `items`
- `qr_codes`
- `notification_urls`

O QR é criado no endpoint:

```text
POST https://sandbox.api.pagseguro.com/orders
```

ou em produção:

```text
POST https://api.pagseguro.com/orders
```

O webhook é enviado automaticamente como:

```text
{REDSEBIA_PUBLIC_BASE_URL}/api/payments/webhooks/pagseguro_pix
```

Você não precisa cadastrar essa URL manualmente no painel do PagBank para este fluxo específico, porque o REDSEBIA já a inclui no próprio pedido via `notification_urls`.

## Passo a passo no REDSEBIA

### 1. Abrir o admin

Entre em:

```text
http://SEU_HOST/redsebia/admin
```

### 2. Configurar o método

No card **PagBank PIX**:

1. marque **Ativar método**;
2. em `Ambiente`, escolha `sandbox` ou `production`;
3. cole o `Token`;
4. preencha `CPF padrão (fallback)`;
5. opcionalmente preencha `DDD` e `Telefone`;
6. clique em **Salvar configuração**.

### 3. Testar no portal do cliente

Abra:

```text
http://SEU_HOST/redsebia/portal
```

Depois:

1. selecione `PagBank PIX`;
2. informe um valor;
3. clique em **Gerar cobrança**.

## O que deve acontecer se estiver tudo certo

Se a integração estiver saudável, o portal deve mostrar:

- QR Code;
- código PIX / texto do QR;
- cobrança em `pending`;
- método `PagBank PIX`.

No backend, a cobrança vai guardar:

- `provider_charge_id`
- `qr_code`
- `qr_code_base64`
- payload bruto do pedido

## Checklist rápido de sucesso

Você está integrado de verdade quando estas 4 coisas acontecem:

1. o card `PagBank PIX` salva sem erro;
2. o cliente consegue gerar cobrança sem `400`;
3. o portal exibe QR Code;
4. o webhook ou refresh move a cobrança quando o pagamento acontece.

## Erros mais comuns

### 1. `401 Invalid credential`

Quase sempre é um destes:

- token copiado errado;
- token de sandbox com ambiente `production`;
- token de produção com ambiente `sandbox`;
- token revogado/expirado.

### 2. Gera cobrança mas não aparece QR

Normalmente é:

- conta sem chave PIX ativa;
- resposta do PagBank sem os links do QR;
- token sem acesso válido para esse fluxo.

### 3. `400` ao gerar cobrança

Os casos mais prováveis hoje no REDSEBIA:

- CPF ausente no cliente **e** `CPF padrão (fallback)` vazio;
- token inválido;
- payload recusado pelo PagBank;
- ambiente configurado errado.

### 4. Cobrança cria, mas saldo não entra

Neste caso o problema normalmente está em um destes pontos:

- webhook não chegou na VM;
- `REDSEBIA_PUBLIC_BASE_URL` está errado;
- o pagamento ainda não foi confirmado pelo PagBank;
- a cobrança precisa ser atualizada por refresh.

## Boas práticas

- use `sandbox` primeiro;
- só passe para `production` quando o QR já estiver aparecendo e o fluxo estiver consistente;
- mantenha o `CPF padrão (fallback)` só como apoio, não como solução final;
- deixe o `REDSEBIA_PUBLIC_BASE_URL` apontando para a URL pública real do serviço.

## Diagnóstico rápido na VM

### Ver se o serviço está vivo

```bash
systemctl status red-sebia --no-pager
```

### Ver logs recentes

```bash
journalctl -u red-sebia -n 100 --no-pager
```

### Healthcheck

```bash
curl -s http://127.0.0.1:3130/healthz
```

## Fluxo recomendado de teste

1. configurar `PagBank PIX` em `sandbox`;
2. salvar;
3. criar uma conta cliente de teste;
4. gerar uma cobrança de valor baixo;
5. confirmar que:
   - a cobrança foi criada;
   - o QR apareceu;
   - o método marcado foi `PagBank PIX`.

Se falhar já no passo 4, o primeiro suspeito é sempre:

- token inválido; ou
- ambiente errado.

## Links oficiais

- Token de autenticação: https://developer.pagbank.com.br/docs/token-de-autenticacao
- Criar pedido com QR Code (PIX): https://developer.pagbank.com.br/reference/criar-pedido-pedido-com-qr-code
- Criar pedido: https://developer.pagbank.com.br/docs/criar-pedido-simples

