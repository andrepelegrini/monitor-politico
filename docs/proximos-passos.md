# Próximos passos

Onde o projeto está e o que vem depois. Atualizado em 14/11/2026.

O site se chama **Na Galeria** e está em https://www.nagaleria.com.br (domínio na GoDaddy, DNS na Cloudflare, hospedagem na Vercel). O endereço antigo `monitor-politico-eight.vercel.app` redireciona para o novo. O repositório continua `monitor-politico`.

Ideias soltas anotadas durante o uso ficam em [notes.txt](../notes.txt).

## Já no ar

- **Página inicial**: destaques por regra fixa com resumo em linguagem simples, pauta dos próximos dias, assuntos do mês e entrada por estado (mapa e 27 páginas de estado).
- **Votações**: todos os projetos com o texto votado no Plenário desde fevereiro de 2023, com filtro de período, e uma página para cada um.
- **Deputados e senadores**: lista comparável (leis, votos, presença ou participação, relatorias), mapa das bancadas, perfil completo, retrospectiva da legislatura 2023–2027, eleitos para 2027, badges da eleição de 2026 e quem está fora de exercício.
- **Resumos por IA**: Sonnet 5.5, só o texto do PDF, para as proposições dos últimos 30 dias e da pauta e para as PECs do histórico.
- **Busca única no topo**, página **"Entenda os dados"**, **identidade visual** (logo, cabeçalho azul-marinho) e **pré-visualização ao compartilhar**.

## Pendências

- [ ] Conferir a pré-visualização ao compartilhar: colar o link de uma página no WhatsApp. Se não aparecer imagem, cadastrar `SITE_URL` com o domínio do site nas variáveis de ambiente do projeto na Vercel.
- [ ] Testar no celular o botão de baixar a imagem da retrospectiva (deve abrir o compartilhamento do sistema).
- [ ] Conferir os 10 senadores marcados como "Sem candidatura em 2026" e testar o site com leitor de tela.

## Em andamento: perfil completo para todos

- [x] Piloto com Tabata Amaral e publicação, em 05/11/2026.
- [x] 6C, legislatura de 2027: badges, eleitos e quem está fora de exercício.
- [x] 6A, perfil completo para os deputados em exercício: publicado em 06/11/2026.
- [x] 6B, senadores: publicado em 07/11/2026. Conferir a primeira coleta automática do Senado (segunda, 09/11) e os 10 marcados como "Sem candidatura em 2026". Perfil completo, lista comparável, eleitos e badges. Coleta em `lote_senado.py`.
- [x] Página inicial v2 (10/11/2026): destaques por regra fixa, pauta com títulos simples, assuntos do mês, entrada por estado, 27 páginas de estado e a lista completa em votacoes.html. Resumos por IA ligados (segredo ANTHROPIC_API_KEY). Próximas etapas do plano: assuntos agrupados, busca simples, comparar lado a lado e custo do mandato, acompanhar temas.
- [x] Custo dos resumos por IA (11/11/2026): só o texto do PDF, raciocínio baixo, consumo registrado em cada resumo e modelo trocado para o Sonnet 5.5 após teste com 8 proposições (Opus US$ 0,082, Sonnet US$ 0,041, Haiku US$ 0,002 por resumo; Haiku falhou em 2 de 8). Estimativa: US$ 3 a 5 por mês. Para cortar mais: limitar o texto de proposições muito longas.
- [x] Retrospectiva da legislatura 2023–2027 (11/11/2026): uma página por parlamentar em `deputados/retrospectiva/` e `senadores/retrospectiva/`, com referências da Casa (mediana e contagens só entre quem exerceu ao menos 3/4 do período) e imagens de feed e stories desenhadas no navegador. Os números se atualizam toda semana; na posse, fechar a versão final.
- [x] Histórico de votações (11/11/2026): `historico.py`, na coleta semanal, gera `data/historico.json` com os 946 projetos com o texto votado no Plenário desde 01/02/2023. Cada um tem página, entra na busca e na página de Votações (filtro de período). Só as PECs do histórico ganham resumo por IA. A lista de quem votou como, nas votações antigas, fica só nos perfis. Votações simbólicas do Senado não existem na fonte.
- [ ] Etapa 2, assuntos agrupados: a base agora existe (histórico acima). Falta decidir o agrupamento, por palavras-chave revisadas pelo usuário ou por IA a partir das ementas, e fazer o mock.

Como funciona: `lote.py` coleta todos numa passada só e `pacote.py` empacota em um anexo da release `dados-perfis`, porque são centenas de MB que mudam toda semana. O Git guarda só `data/perfis_versao.json`, com o nome e o checksum. O build da Vercel baixa essa versão, e se o download falhar o build falha e o site continua como está. O robô `perfis.yml` faz isso toda segunda. Rodar à mão: `gh workflow run perfis.yml`.

Cuidado com a cota: os arquivos abertos da Câmara oscilam. As passagens aéreas do SIGEPA estavam lá em 04/11/2026, sumiram em 05/11 e voltaram em 06/11. Por isso o total vem da página oficial do deputado, e o que falta no arquivo aparece como "sem detalhamento".

Propostas de campanha: o TSE só recebe proposta de governo de candidaturas a presidente, governador e prefeito. Deputados e senadores não registram proposta nenhuma, então essa comparação depende de outra fonte, a definir.

As cores dos badges e dos resultados de votação estão em `static/estilo.css`, e foram aprovadas em 06/11/2026. São categorias, sem verde e vermelho como certo e errado. Comparar parlamentares é desejado quando a métrica é objetiva.

A lista de deputados mostra leis, votos, presença e relatorias atuais. As relatorias não usam o total oficial da Câmara, porque ele inclui requerimentos de informação que a Mesa relata aos milhares (10.959 para um único deputado) e concessões de rádio e TV.

Na posse, em 01/02/2027: trocar `INICIO_MANDATO` em `metricas.py` e `LEGISLATURA_ATUAL`, `ANO_DA_ELEICAO` e `POSSE` em `legislatura.py`, rodar as coletas manuais e ligar as páginas dos eleitos (`deputados/eleitos/`) aos novos perfis, com redirecionamento. A coleta diária já move para o arquivo quem sair da lista de exercício.

## Backlog (features sem IA)

Ordem combinada: 5 (feito) → 1 junto com 4 → 2 → 3. Antes de cada uma, fazer um mock para aprovação.

1. ~~**Atuação no perfil do parlamentar**~~ (entregue: perfil completo, 6A e 6B).
2. ~~**Retrospectiva do mandato compartilhável**~~ (entregue em 11/11/2026): página por parlamentar com os números do mandato e uma imagem para redes gerada na coleta. Os mandatos atuais terminam em 31/01/2027, então o ideal é lançar antes. Depende do item 1.
3. ~~**Resultado eleitoral (TSE)**~~ (entregue: eleições 2018–2026 no perfil, badges de 2026 e eleitos para 2027).
4. **"Acompanhar" sem servidor próprio**: feeds RSS por parlamentar e por proposição, gerados no build. Alertas por e-mail exigem servidor e ficam como candidatos à versão paga.
6. **Avisos da nova legislatura e contato**: mock aprovado em 07/11/2026, nas posições Eleitos para 2027, perfil de quem chega e página inicial, mais "Encontrou um erro?" nos perfis e no rodapé. Falta criar um Gmail do projeto e um Google Forms com planilha privada (nunca um link direto para a planilha), e definir o nome do responsável para a política de privacidade. Na hora de enviar: cópia oculta, atenção ao limite diário do Gmail e apagar a lista depois, como o texto promete.
7. ~~**Domínio próprio**~~ (entregue em 14/11/2026: nagaleria.com.br). Falta o e-mail `contato@nagaleria.com.br` pelo Email Routing da Cloudflare, encaminhando para o Gmail do projeto.
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
