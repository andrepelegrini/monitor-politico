# Próximos passos

Onde o projeto está e o que vem depois. Atualizado em 04/11/2026.

Ideias soltas anotadas durante o uso ficam em [notes.txt](../notes.txt).

## Já no ar

- **Deputados e senadores**: lista por Casa com filtros e resumo (partidos, estados, quem conduz a Casa) e perfil de cada parlamentar com contato oficial. Gênero aparece só como contagem agregada.
- **Página inicial**: temas em destaque, pauta dos próximos dias e o que foi votado nos últimos 30 dias.
- **Página de cada proposição**: ementa, linha do tempo, votações, orientação dos partidos e voto de cada parlamentar (só nas votações nominais).
- **Busca única no topo** (parlamentares e proposições), **página "Entenda os dados"** e **pré-visualização ao compartilhar** (Open Graph).
- **Resumos por IA das proposições**: o código está pronto (`resumos_ia.py` → `data/resumos.json`), mas ainda não rodou. Veja as pendências.

## Pendências

- [ ] Cadastrar o secret `ANTHROPIC_API_KEY` no GitHub (Settings → Secrets and variables → Actions) para os resumos por IA serem gerados na coleta diária. A IA ficou para depois, talvez numa versão paga, então isso não é urgente.
- [ ] Conferir a pré-visualização ao compartilhar: colar o link de uma página no WhatsApp. Se não aparecer imagem, cadastrar `SITE_URL` com o domínio do site nas variáveis de ambiente do projeto na Vercel.

## Em andamento: novo perfil de parlamentar (branch `perfil-piloto`)

Piloto só na página de Tabata Amaral (id 204534). Nenhum outro parlamentar recebe o perfil novo sem autorização: `perfis.PILOTO` e um teste travam isso, e as demais páginas continuam com os templates atuais.

- [x] Etapa 0: estrutura e mock.
- [x] Etapa 1: Quem é (eleições, votos por município, bens, trajetória e comissões).
- [x] Etapa 2: atuação em Plenário (votos e presença).
- [x] Etapa 3: dinheiro público (cota e emendas).
- [x] Etapa 4: propostas e leis. Aguardando validação.
- [ ] Etapa 5: leitura e compartilhamento.
- [ ] Rollout, com autorização: 6A deputados, 6B senadores, 6C legislatura de 2027. A 6C precisa estar pronta até o início de janeiro, porque a coleta atual lista só quem está em exercício e a nova legislatura começa em 01/02/2027.

Cuidado com a cota: os arquivos abertos da Câmara oscilam. Em 04/11/2026 traziam as passagens aéreas do SIGEPA até julho de 2025; em 05/11/2026, em nenhum ano. Por isso o total vem da página oficial do deputado, e o que falta no arquivo aparece como "sem detalhamento".

Atualizar os dados do piloto: `.venv/bin/python -m monitor_politico.perfis` (leva alguns minutos e fica fora do robô diário).

## Backlog (features sem IA)

Ordem combinada: 5 (feito) → 1 junto com 4 → 2 → 3. Antes de cada uma, fazer um mock para aprovação.

1. **Atuação no perfil do parlamentar** (em andamento no piloto acima): votos nas votações nominais e presença (a coleta é nova: `data/congresso.json` só tem 30 dias e nenhuma presença); proposições de autoria (Câmara `/proposicoes?idDeputadoAutor`, Senado `/processo` por autor); gastos da cota parlamentar (Câmara `/deputados/{id}/despesas`; o Senado publica a CEAPS em arquivo).
2. **Retrospectiva do mandato compartilhável**: página por parlamentar com os números do mandato e uma imagem para redes gerada na coleta. Os mandatos atuais terminam em 31/01/2027, então o ideal é lançar antes. Depende do item 1.
3. **Resultado eleitoral (TSE)**: votos em 2022 e resultado de 2026 (reeleito, não concorreu, não eleito). Os arquivos são grandes e separados por UF; confirmar o que o TSE já publicou de 2026.
4. **"Acompanhar" sem servidor próprio**: feeds RSS por parlamentar e por proposição, gerados no build. Alertas por e-mail exigem servidor e ficam como candidatos à versão paga.
5. ~~**Melhorias rápidas**: busca única, "Entenda os dados", Open Graph.~~ Entregue em 03/11/2026.

Fora do escopo por enquanto: deputados estaduais e governadores (27 assembleias com formatos diferentes) e contador de visitantes (se quiser, usar o Vercel Analytics).

## Decisões que valem para o projeto todo

- Só dados oficiais, sem avaliação nem opinião sobre ninguém.
- Coleta uma vez por dia, às 6h de Brasília, só em dias úteis.
- Conteúdo gerado por IA vem sempre rotulado, com a ementa oficial ao lado.
- Limites das fontes: só cerca de 3 das ~39 votações mensais de plenário da Câmara são nominais. A API do Senado só lista as votações nominais e não publica a orientação dos partidos.

## Como trabalhar no projeto

- Repositório: `github.com/andrepelegrini/monitor-politico` (público). Neste computador, o push usa o alias SSH `github.com-personal`.
- Hospedagem: Vercel, com deploy a cada push na `main`. A coleta diária roda no GitHub Actions e faz commit dos arquivos em `data/`. Faça `git pull` antes de começar, porque o robô de coleta envia commits todo dia útil.
- Visual: design system Civic Editorial em `design-system/` (leia `design-system/ai/AGENT_INSTRUCTIONS.md` antes de mexer no frontend). `static/ce-*.css` são cópias exatas do pacote, e um teste confere isso: para alterá-los, mude em `design-system/` e copie. O que é só deste site fica em `static/estilo.css`, usando os tokens `--ce-*`.
- Rodar localmente: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`, depois `.venv/bin/python -m pytest` e `.venv/bin/python -m monitor_politico.build` (gera o site em `site/`).
