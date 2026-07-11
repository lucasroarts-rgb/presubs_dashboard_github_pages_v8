# Correção: excluir Quiz Registrations

Esta versão aplica três proteções obrigatórias:

1. A campanha precisa conter `PRESUBS`.
2. Campanhas, conjuntos e anúncios com `QUIZ`, `QUIZ REGISTRATION` ou `QUIZ REGISTRATIONS` no nome são ignorados.
3. A métrica de resultado aceita somente `offsite_conversion.fb_pixel_complete_registration`. Eventos `Lead` não entram como registros.

## Importante para o histórico já iniciado

Interrompa a importação antiga. Depois de migrar para esta versão, execute:

`REIMPORTAR_HISTORICO_2026.bat`

O modo de reimportação apaga e recria cada semana, removendo o investimento e as métricas dos Quiz do banco.

## Migração

Execute `MIGRAR_DO_V9_2.bat` e selecione a pasta atual. O token, banco e conexão do GitHub serão preservados.
