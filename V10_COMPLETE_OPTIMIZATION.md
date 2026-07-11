# PreSubs Dashboard v10

This release combines the corrected Meta scope with the complete management layer.

## Meta scope

- Campaign name must contain `PRESUBS`.
- Campaigns, ad sets and ads containing `QUIZ`, `QUIZ REGISTRATION` or `QUIZ REGISTRATIONS` are excluded.
- Registrations use only `offsite_conversion.fb_pixel_complete_registration`.
- Lead and Quiz Registration events are never counted as Complete Registrations.

## Management improvements

### Automatic alerts

Rules cover spend without registration, CPL above target, CTR decline, high frequency, click-to-LPV loss, page-conversion decline, days without registration and launch projection risk.

### Goals and projections

The local admin stores target CPL, total budget, registration target, launch dates and alert thresholds. The public dashboard receives only those planning values, not credentials or the SQLite database.

### Creative health

Ads are classified as `Scale`, `Keep`, `Monitor`, `Refresh` or `Pause candidate`, using the last 3 and 7 days, total history, frequency, CTR and CPL.

### Landing-page funnel

Each page shows link clicks, landing-page views, Complete Registrations, click-to-LPV rate, LPV-to-registration rate, spend and CPL.

### Timeline annotations

Budget, creative, landing-page, email and launch events can be registered in the local admin and published alongside the date analysis.

### Data quality

Checks cover daily coverage, weekly-versus-daily totals, campaign-versus-ad spend, missing relations, page tagging, LPV availability and Quiz exclusion.

### Executive summary

The Overview creates a concise interpretation of spend, registrations, CPL, strongest campaign, strongest page and alert volume.

### Presentation mode

The presentation button hides technical controls and focuses the dashboard on decision-level content.

### Scheduled automation

`AGENDAR_AUTOMACAO_SEMANAL.bat` creates a Friday Windows task. The task runs the existing Meta API → SQLite → QA → GitHub Pages flow.

## Required migration

1. Let the current historical download finish or stop it safely.
2. Extract v10 to a new folder.
3. Run `MIGRAR_DA_VERSAO_ATUAL.bat`.
4. Select the folder currently holding `.env`, `.git` and `data/presubs.db`.
5. Run `REIMPORTAR_HISTORICO_2026.bat` so every week is rebuilt with Quiz exclusion.
6. Open `START_LOCAL_DASHBOARD.bat` and configure goals and annotations in `/admin`.
7. Run `PUBLICAR_NO_GITHUB.bat`.
