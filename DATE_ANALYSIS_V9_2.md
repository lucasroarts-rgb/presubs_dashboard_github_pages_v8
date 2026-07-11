# PreSubs Dashboard v9.2 – Date analysis

This version adds a full **Date analysis** view while preserving the existing visual and all v9.1 automation.

## New analysis

- Custom start and end dates
- Latest 7, 30 and 90 days
- Latest month to date
- Previous calendar month
- Year to date
- All available history
- Comparison with the immediately preceding period of the same length
- Same dates in the previous month
- Same dates in the previous year
- Two custom comparison ranges
- Trend by day, Friday–Thursday week or month
- Month-over-month table
- Campaign, ad set, ad and conversion-page breakdowns
- Campaign and page comparison tables
- Weekday performance
- CSV export of the selected detailed rows
- Coverage warning for missing daily dates

Reach and frequency are not aggregated in custom ranges because daily reach cannot be safely summed.

## Migration

Let the current v9.1 historical import finish. Then:

1. Extract v9.2 to a new folder.
2. Run `MIGRAR_DO_V9_1.bat`.
3. Select the v9.1 folder that finished the historical download.
4. Run `GERAR_SITE_PUBLICO.bat`.
5. Run `PUBLICAR_NO_GITHUB.bat`.

The migration copies the local database, Meta `.env`, audit exports, logs and the existing GitHub connection. The public URL stays the same.

## Static export optimization

Earlier versions generated every possible week-to-week comparison inside `data.js`. With a full year of history, that grows quadratically. v9.2 calculates weekly comparisons in the browser from the already published weekly datasets, reducing the public payload substantially.
