# v10.6.3 — Audit data scope fix

## Problem fixed

The Audit Overview could show top-level spend and registration totals while the
campaign breakdown, funnel diagnostics, creative mix, bubble chart, Pareto and
Period Intelligence were empty.

The cause was that some Audit components relied only on weekly aggregate arrays
or on the cached historical daily dataset. When a newly imported current week
was fresher than that cache, the latest daily rows were ignored.

## Fix

- The current dashboard's fresh daily rows are merged with historical daily rows.
- Current-period rows always take priority over older cached copies.
- Audit campaign, ad-set and ad views are rebuilt from selected-period daily rows
  when those rows are available.
- Campaign breakdown, funnel diagnostics, creative mix, spend-vs-CPL, waste and
  opportunity Pareto now use the same selected-period source.
- Period Intelligence uses the same merged data source.
- The selected period displays the latest available data date.

No Meta data is invented. Weekly aggregates remain the fallback when daily rows
are unavailable.
