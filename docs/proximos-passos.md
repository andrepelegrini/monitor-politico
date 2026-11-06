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

## Em andamento: perfil completo para todos

- [x] Piloto com Tabata Amaral e publicação, em 05/11/2026.
- [x] 6C, legislatura de 2027: badges, eleitos e quem está fora de exercício.
- [ ] 6A, perfil completo para os deputados em exercício (branch `rollout-6a`). Aguardando validação.
- [ ] 6B, senadores.

Como funciona: `lote.py` coleta todos numa passada só e `pacote.py` empacota em um anexo da release `dados-perfis`, porque são centenas de MB que mudam toda semana. O Git guarda só `data/perfis_versao.json`, com o nome e o checksum. O build da Vercel baixa essa versão, e se o download falhar o build falha e o site continua como está. O robô `perfis.yml` faz isso toda segunda. Rodar à mão: `gh workflow run perfis.yml`.

Cuidado com a cota: os arquivos abertos da Câmara oscilam. As passagens aéreas do SIGEPA estavam lá em 04/11/2026, sumiram em 05/11 e voltaram em 06/11. Por isso o total vem da página oficial do deputado, e o que falta no arquivo aparece como "sem detalhamento".

Propostas de campanha: o TSE só recebe proposta de governo de candidaturas a presidente, governador e prefeito. Deputados e senadores não registram proposta nenhuma, então essa comparação depende de outra fonte, a definir.

As cores dos badges e dos resultados de votação estão em `static/estilo.css`, e foram aprovadas em 06/11/2026. São categorias, sem verde e vermelho como certo e errado. Comparar parlamentares é desejado quando a métrica é objetiva.

Na posse, em 01/02/2027: trocar `INICIO_MANDATO` em `metricas.py` e `LEGISLATURA_ATUAL`, `ANO_DA_ELEICAO` e `POSSE` em `legislatura.py`, rodar as coletas manuais e ligar as páginas dos eleitos (`deputados/eleitos/`) aos novos perfis, com redirecionamento. A coleta diária já move para o arquivo quem sair da lista de exercício.

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
