# Regras do projeto PreSubs_Weekly_Dashboard (Peasy)

Carrega junto com o CLAUDE.md global (`~/.claude/CLAUDE.md`) — regras globais (adhd, caveman ultra, etc.) continuam valendo aqui, essas são adicionais só pra esse projeto.

## GitHub deste projeto

Remote/identidade corretos pra esse repo (deploy do dashboard, review decks, etc.): conta **lucasroarts-rgb** (`lucasro.arts@gmail.com`), repo `https://github.com/lucasroarts-rgb/presubs_dashboard_github_pages_v8`. Sempre que precisar commitar/pushar/abrir PR nesse projeto, usar essa conta — não trocar remote/identidade sem pedido explícito.

## skills pro projeto — analisado em 2026-09-18

Stack real do projeto (checado direto): FastAPI + pandas + pymysql (MySQL CRM) + Playwright + Google Analytics Data API (GA4) + Google Search Console + Google Ads API, front estático GitHub Pages, gera review decks (weekly_reviews/, l24_reviews/).

Skills instaladas pra ele — usar PROATIVAMENTE sempre que a tarefa se aplicar, sem esperar comando explícito do tipo "usa a skill X".

**IMPORTANTE (2026-09-18, corrigido depois de eu ter instalado tudo e não usado nenhuma na prática):** invocar de verdade via Skill tool, não só ter a skill instalada como referência mental. Não fazer manual (curl/grep/screenshot solto) quando a skill cobre a tarefa — chamar a skill primeiro e seguir o fluxo dela até o fim (não abandonar no meio se distrair com outra coisa). Antes de qualquer mudança de CSS/HTML/layout nas landing pages ou no dashboard: `design:accessibility-review` e/ou `web-design-guidelines` primeiro, sem exceção.
- **`data:*`** (analyze, build-dashboard, create-viz, explore-data, sql-queries, statistical-analysis, validate-data, data-context-extractor) — qualquer análise, query SQL na base MySQL/CRM, construção/ajuste do dashboard, gráfico novo.
- **`searchfit-seo:*`** (seo-audit, technical-seo, on-page-seo, keyword-clustering, content-strategy, schema-markup, broken-links, ai-visibility, content-brief, internal-linking) — qualquer trabalho envolvendo os dados de GSC (Search Console) que o projeto já integra, ou SEO do blog WordPress ligado a ele.
- **`marketing:*`** (performance-report, campaign-plan, content-creation, brand-review, seo-audit) — geração dos review decks semanais/L24 (weekly_reviews, l24_reviews), relatório de performance cross-canal.
- **`dataviz`** (já disponível, sem instalação) — SEMPRE antes de escrever qualquer gráfico/chart/dashboard novo nesse projeto (regra própria do skill: ler antes da primeira linha de código de chart).
- **`design:*`** (accessibility-review, design-critique, design-handoff, design-system, ux-copy, research-synthesis, user-research) — qualquer ajuste visual/UX no dashboard (front estático em `static/`), auditoria de acessibilidade, revisão de layout/hierarquia antes de mexer em CSS/HTML.
- **`web-design-guidelines`** (já disponível, sem instalação) — revisão rápida de UI/acessibilidade/UX best practices, usar em qualquer mudança de tela do dashboard ou das landing pages.
- **`adspirer-ads-agent:*`** (adspirer-meta-ads, adspirer-google-ads, adspirer-launch, adspirer-optimize, adspirer-creative, adspirer-performance-review, adspirer-setup, adspirer-get-started) — instalado de verdade em 2026-09-20 (marketplace GitHub `amekala/adspirer-mcp-plugin`, plugin real chama `adspirer-ads-agent`, não `adspirer`). Usar em QUALQUER trabalho de lançamento/otimização/performance de Meta Ads ou Google Ads (ex: L24), junto com o conector Meta MCP direto na conta — o Adspirer não substitui esse conector, complementa (ex: `analyze_meta_wasted_spend`, `analyze_search_terms` do Google Ads). Ferramentas do Adspirer em si pedem OAuth — se aparecer bloqueado por autenticação, avisar o usuário que precisa autorizar em claude.ai/customize/connectors ou `/mcp` numa sessão interativa, não dá pra fazer sozinho numa sessão não-interativa. Rodar `adspirer-setup`/`adspirer-get-started` antes do primeiro uso real pra conectar as contas.
