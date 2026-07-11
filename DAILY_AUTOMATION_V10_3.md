# Daily automation and sidebar, v10.3

## Daily update

Run `AUTOMATIZAR_DIARIO.bat` to test the new flow manually.

The daily process:

1. Reads the Meta ad-account timezone.
2. Uses the previous completed calendar day.
3. Rebuilds the active Friday-to-Thursday reporting week.
4. Excludes Quiz campaign, ad-set and ad names.
5. Counts only the exact Pixel CompleteRegistration event.
6. Updates SQLite.
7. Rebuilds `docs`.
8. Synchronizes and publishes GitHub Pages.

## Schedule at 06:00 Brazil time

Run `AGENDAR_AUTOMACAO_DIARIA_0600.bat` as administrator.

The default is 06:00 in the Windows local timezone. The computer must be on,
connected to the internet and authenticated with GitHub.

To remove the task, run `REMOVER_AUTOMACAO_DIARIA.bat`.

## Daily briefing

The new Daily briefing page shows:

- latest completed day
- previous-day comparison
- monthly daily pacing
- last 14 days
- best ads
- ads needing attention
- campaign snapshot
- conversion-page snapshot

## Meta temporary errors

The API now makes longer retries and, after a persistent account-level server
error, repeats the report campaign by campaign. This reduces the report size
without changing the date range or entity level.
