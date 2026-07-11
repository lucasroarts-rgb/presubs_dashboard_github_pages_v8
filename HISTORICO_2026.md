# Importação histórica de 2026

Use `IMPORTAR_HISTORICO_2026.bat` para preencher todas as semanas completas de
2026, da primeira sexta-feira do ano até a última quinta-feira concluída.

Em 2026, o primeiro período completo é:

`02/01/2026 a 08/01/2026`

O dia 01/01 não é criado como uma semana isolada, porque o dashboard trabalha
com períodos padronizados de sexta-feira a quinta-feira.

## O que acontece

1. O banco SQLite recebe um backup em `backups`.
2. A Meta é consultada uma semana por vez.
3. Apenas campanhas cujo nome contém `PRESUBS` entram no histórico.
4. Para cada semana são baixados campanhas, conjuntos, anúncios e anúncios por dia.
5. Cada período é salvo imediatamente no SQLite.
6. O progresso é registrado em `logs`.
7. A pasta `docs` é gerada somente no final.
8. É feito apenas um commit e um push para o GitHub.

## Retomar após uma falha

Execute novamente `IMPORTAR_HISTORICO_2026.bat`.

As semanas concluídas pelo importador histórico são ignoradas e o processo
continua da primeira semana pendente.

## Reimportar tudo

Use `REIMPORTAR_HISTORICO_2026.bat` para baixar novamente todas as semanas,
inclusive as já concluídas.

## Escolher outra data

Use `IMPORTAR_HISTORICO_DESDE_DATA.bat` e informe a data inicial.

O sistema ajusta o início para a primeira sexta-feira disponível e encerra na
última quinta-feira concluída, caso a data final fique em branco.

## Conversion scope

Only the exact Meta Pixel `CompleteRegistration` action is counted. Campaigns, ad sets and ads containing `QUIZ` in their names are excluded, even when the campaign name also contains `PRESUBS`.
