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

## Conversion scope

Only the exact Meta Pixel `CompleteRegistration` action is counted. Campaigns, ad sets and ads containing `QUIZ` in their names are excluded, even when the campaign name also contains `PRESUBS`.

## v10 complete management optimization

The v10 package combines the corrected CompleteRegistration-only scope with alerts, goals, projections, Creative health, page funnels, timeline annotations, quality checks, executive summary, presentation mode and Windows scheduling.

Run `MIGRAR_DA_VERSAO_ATUAL.bat`, then reimport the 2026 history with `REIMPORTAR_HISTORICO_2026.bat` before publishing.

See `V10_COMPLETE_OPTIMIZATION.md`.


## Monthly goals

Version 10.1 stores one goal per month and automatically derives daily and Friday-to-Thursday weekly targets. Historical goal-versus-actual performance remains available for every month. See `MONTHLY_GOALS_V10_1.md`.


## v10.3 daily workflow

Use `AUTOMATIZAR_DIARIO.bat` for a manual daily update and
`AGENDAR_AUTOMACAO_DIARIA_0600.bat` to schedule it every day at 06:00.

The public dashboard now uses a responsive icon sidebar and includes a separate
Daily briefing page. See `DAILY_AUTOMATION_V10_3.md`.


## v10.3.1 daily briefing hotfix

Fixes the missing alert severity helpers that prevented the advanced rendering chain from reaching the Daily briefing page.


## v10.3.1 student profile and Peasy branding

- Adds the Peasy Anglais logo to the sidebar and top bar.
- Adds a Student profile menu with aggregated Academy and Fluency Club placement-test insight.
- Removes repeated scope labels from the hero and sidebar.
- Includes the Daily briefing JavaScript correction from v10.3.1.

See `STUDENT_PROFILE_V10_3_1.md`.


## v10.4 audit overview

The new first page is an audit-style Meta Ads overview. See `AUDIT_OVERVIEW_V10_4.md`.


## v10.5 interactive audit
See `INTERACTIVE_AUDIT_V10_5.md` for animated charts, annotation markers and the automatic before/after meeting recap.

## v10.6: custom day ranges, languages and meeting intelligence

- Global period selector now supports full imported weeks or any custom date interval from the available daily Meta history, such as 05 Jul to 07 Jul.
- Custom ranges automatically compare against the immediately preceding period with the same number of days.
- Interface language selector: English (default), French and Portuguese. Number and date formatting follow the selected language.
- The global campaign-performance hero is hidden on Student Profile because the placement-test audience data is not tied to the selected Meta reporting period.
- Audit Overview now includes Period intelligence: best registration day, strongest campaign, top creative, leading conversion page, top-3 spend concentration and weekday performance.
- Reach and frequency are intentionally shown as unavailable for custom multi-day ranges when they cannot be safely reconstructed from daily data.
