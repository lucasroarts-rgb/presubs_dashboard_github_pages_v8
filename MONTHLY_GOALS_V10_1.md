# Monthly goals v10.1

Goals are now stored month by month. Each record contains:

- Month (`YYYY-MM`)
- Monthly budget
- Monthly registration target
- Target CPL
- Optional note

The dashboard automatically calculates daily targets and the proportional target for each Friday-to-Thursday reporting week. Weeks that cross two months use only the days belonging to the selected goal month.

The public dashboard records actual spend, actual registrations, actual CPL, variances and status for every month. Previous monthly targets remain visible and are never overwritten when a new month's goal is added.

## Migration

1. Let the current historical import finish.
2. Extract v10.1 into a new folder.
3. Run `MIGRAR_DA_VERSAO_ATUAL.bat` and select the current v10 folder.
4. Run `START_LOCAL_DASHBOARD.bat`.
5. Add the monthly goals in `/admin`.
6. Run `PUBLICAR_NO_GITHUB.bat`.
