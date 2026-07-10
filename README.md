# PreSubs Weekly Dashboard v8

Esta versão mantém o banco e a importação no seu computador e publica somente o dashboard estático no GitHub Pages.

## Arquivos semanais

Para cada período, use:

1. Campanhas sem detalhamento.
2. Conjuntos de anúncios sem detalhamento.
3. Anúncios sem detalhamento.
4. Anúncios com `Detalhamento > Tempo > Dia`, recomendado.

Os três primeiros arquivos mantêm os totais semanais corretos. O quarto arquivo alimenta a aba **Daily performance**.

## Administração local

Execute:

`START_LOCAL_DASHBOARD.bat`

Abra:

`http://127.0.0.1:8000/admin`

O banco permanece em:

`data/presubs.db`

## Dashboard público

Execute:

`GERAR_SITE_PUBLICO.bat`

A pasta `docs/` será atualizada com:

- Overview
- Weekly comparison
- Campaign structure
- Campaigns
- Ad sets
- Ads
- Daily performance
- Page conversion

Depois, use:

`PUBLICAR_NO_GITHUB.bat`

O GitHub Pages publica somente os resultados agregados e o detalhe de performance dos anúncios. O banco SQLite, as planilhas e as credenciais não são enviados.
