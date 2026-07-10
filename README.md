# PreSubs Weekly Dashboard v7

Esta versão separa a administração local da apresentação pública.

## Local

- FastAPI e SQLite rodam no seu computador.
- As planilhas são importadas em `http://127.0.0.1:8000/admin`.
- O banco permanece em `data/presubs.db`.

Execute:

`START_LOCAL_DASHBOARD.bat`

## GitHub Pages

Execute:

`GERAR_SITE_PUBLICO.bat`

O script lê o SQLite local e gera em `docs/` uma versão estática completa com:

- Overview
- Weekly comparison
- Campaign structure
- Campaigns
- Ad sets
- Ads
- Page conversion

A versão pública não contém o banco, as planilhas, credenciais ou dados pessoais de leads. Ela contém somente os dados agregados que aparecem no dashboard.

Depois de configurar o repositório e o GitHub Pages, use:

`PUBLICAR_NO_GITHUB.bat`

Para conferir a versão estática antes de publicar:

`VER_SITE_PUBLICO.bat`


## One-click Meta automation

The v9 package can pull the four required datasets directly from the Meta
Marketing API, update SQLite, regenerate `docs`, commit and push to GitHub.

Run `MIGRAR_DO_V8.bat`, then `CONFIGURAR_META.bat` once. Weekly updates use
`AUTOMATIZAR_SEMANA.bat`.

See `AUTOMACAO_META_GITHUB.md` for the complete workflow.


## v9.2 date analysis

Run `MIGRAR_DO_V9_1.bat` after the historical import finishes. The new Date analysis tab supports custom dates, period comparison, month-over-month analysis, weekday performance and CSV export. See `DATE_ANALYSIS_V9_2.md`.
