# v10.6.4 — Audit Overview rendering fix

## Root cause

The Audit Overview renderer used the local variable name `t` for the selected-period
totals. The dashboard also uses `t()` as the translation function.

The renderer successfully populated the header totals and then attempted to execute:

`t("Overall")`

At that point `t` referred to the totals object instead of the translation function,
which caused a JavaScript runtime error and stopped the rest of the Audit rendering.

That is why these sections stayed blank even though the top totals were visible:

- Health radar
- Findings by severity
- Category score vs target
- Audit scorecards
- Performance Pulse
- Campaign breakdown
- Funnel diagnostics
- Creative mix
- Spend vs CPL
- Pareto charts
- Findings and action plan

## Fix

The selected-period totals variable is now named `totals`, leaving `t()` available
for translations. The whole Audit renderer can continue normally.

No Meta data, SQLite database, token, goals, annotations, or historical imports are changed.
