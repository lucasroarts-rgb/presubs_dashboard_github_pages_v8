# Automação Meta Ads → SQLite → GitHub Pages

Esta versão reduz o processo semanal a um único arquivo:

`AUTOMATIZAR_SEMANA.bat`

## O que o Python faz

1. Calcula automaticamente a última semana completa, de sexta-feira a quinta-feira.
2. Baixa os dados diretamente da Meta Marketing API.
3. Busca campanhas, conjuntos e anúncios no total semanal.
4. Busca anúncios detalhados por dia.
5. Identifica campanhas pelo filtro configurado, normalmente `PRESUBS`.
6. Grava os dados no SQLite local.
7. Mantém os links de preview já salvos.
8. Gera a pasta pública `docs`.
9. Cria o commit e envia ao GitHub.
10. Salva CSV, JSON bruto, QA e logs apenas no computador.

## Primeira instalação

### 1. Migrar a versão v8

Execute:

`MIGRAR_DO_V8.bat`

O script copia:

- `data\presubs.db`
- as credenciais locais do admin
- a pasta oculta `.git`, preservando o mesmo repositório e o mesmo endereço público

### 2. Configurar a Meta

Execute:

`CONFIGURAR_META.bat`

Você informará localmente:

- ID da conta de anúncios
- token de acesso da Meta
- filtro do nome das campanhas
- ação usada como registro
- endereço do GitHub Pages

O token é salvo somente em `.env`, que está bloqueado no `.gitignore`.

## Atualização semanal

Execute:

`AUTOMATIZAR_SEMANA.bat`

A data padrão é a última sexta-feira até a última quinta-feira concluída.

## Período específico

Execute:

`ATUALIZAR_PERIODO_ESPECIFICO.bat`

Use datas no padrão:

`YYYY-MM-DD`

## Atualizar sem publicar

Execute:

`ATUALIZAR_SEM_PUBLICAR.bat`

Ele baixa da Meta, atualiza o banco e gera `docs`, mas não executa `git push`.

## Auditoria local

Cada sincronização salva:

- `exports\DATA_INICIAL__DATA_FINAL\campaigns.csv`
- `exports\DATA_INICIAL__DATA_FINAL\adsets.csv`
- `exports\DATA_INICIAL__DATA_FINAL\ads.csv`
- `exports\DATA_INICIAL__DATA_FINAL\daily_ads.csv`
- `exports\DATA_INICIAL__DATA_FINAL\raw_meta.json`
- `exports\DATA_INICIAL__DATA_FINAL\qa_report.json`
- `logs\automation_*.json`

Esses arquivos não são publicados no GitHub.

## Requisitos da Meta

A automação precisa de:

- um aplicativo Meta configurado para Marketing API
- um token que tenha acesso à conta de anúncios
- permissão `ads_read`
- o ID da conta, normalmente no formato `act_123456789`

O script não envia o token ao GitHub e não imprime o token nos logs.

## Conversion scope

Only the exact Meta Pixel `CompleteRegistration` action is counted. Campaigns, ad sets and ads containing `QUIZ` in their names are excluded, even when the campaign name also contains `PRESUBS`.
