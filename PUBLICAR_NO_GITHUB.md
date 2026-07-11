# Publicação no GitHub Pages

## Primeira configuração

1. Execute `GERAR_SITE_PUBLICO.bat`.
2. Abra o GitHub Desktop.
3. Use **File > Add local repository** e selecione esta pasta.
4. Caso ainda não seja um repositório, crie o repositório local quando o GitHub Desktop oferecer essa opção.
5. Clique em **Publish repository**.
6. Para usar GitHub Pages gratuitamente, publique o repositório como público.
7. No GitHub, abra **Settings > Pages**.
8. Em **Build and deployment**, escolha **Deploy from a branch**.
9. Selecione a branch `main` e a pasta `/docs`.
10. Salve e aguarde o endereço aparecer.

O endereço normalmente segue este formato:

`https://SEU-USUARIO.github.io/NOME-DO-REPOSITORIO/`

## Atualização semanal

1. Execute `START_LOCAL_DASHBOARD.bat`.
2. Importe as novas planilhas no `/admin`.
3. Confira os números localmente.
4. Execute `PUBLICAR_NO_GITHUB.bat`.

O script atualiza a pasta `docs`, cria um commit e tenta enviar ao GitHub. Caso o push não funcione, abra o GitHub Desktop e clique em **Push origin**.

## Segurança

Nunca remova as regras do `.gitignore`.

Não publique:

- `data/presubs.db`
- planilhas `.xlsx`
- `data/admin_credentials.txt`
- listas de leads
- e-mails ou telefones

Somente os resultados agregados presentes em `docs/data.js` serão publicados.
