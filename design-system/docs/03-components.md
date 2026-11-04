# Especificação de componentes

Todos os componentes: estados `default/hover/focus-visible/disabled/loading/error` quando aplicável, acessibilidade por teclado, textos reais de backend, tokens CSS.

## Base
- `Topbar` / `Sidebar`: marca, Pesquisa, Semana, Proposições, Votações, Parlamentares; `aria-current=page`.
- `Button`: primary espresso, secondary sand, ghost, link; sem ícone isolado sem rótulo acessível.
- `Badge`: identifica tipo/status **sem** representar valor moral; sinalizar status por texto.
- `Input`, `Select`, `DateRange`, `Filters`, `Pagination`, `Tabs`, `Breadcrumbs`.
- `Table`: coluna cabeçalho semântico, ordenação explicita com aria-sort, caption; filtros e paginação acessíveis.
- `Empty`, `Loading`, `Error`, `PartialData`: especificados em `06-states.md`.

## Domínio legislativo
### `PropositionCard`
Campos: `identificador_oficial`, `titulo`, `ementa_resumida?`, `casa`, `situacao`, `ultimo_evento_em?`, `fonte_url`, `atualizado_em`. Nunca derivar situacao a partir de opinião/editorial.

### `VoteDistribution`
Campos: `votacao_id`, `tipo`, `data`, `casa`, `categorias[]`, `universo/denominador`, `fonte`, `atualizado_em`. Mostrar n e eventualmente percentuais com denominador explícito. Votação simbólica não implica registro nominal de cada parlamentar. Não inferir abstenção de ausências.

### `ParliamentarianProfile`
Campos: `nome_oficial`, `cargo`, `partido_na_data?`, `uf`, `legislatura`, `foto_oficial?`, `fonte`, `data_referencia`, navegação para votações/proposições/comissões. Cuidado com troca de partido e legislaturas históricas. Não atribuir “nota geral” ou ranking político.

### `LegislativeTimeline`
Lista cronológica com `data`, `descricao_oficial`, `resumo?`, `orgao`, `fonte`. Diferenciar concluído, previsto e alterado/cancelado.

### `AgendaEvent`
Data/hora local, fuso, casa/órgão, tipo, pauta, link oficial e status da previsão. Sinalizar alterações de agenda.

### `OfficialSource`
Perto de qualquer dado relevante: documento/endpoint, data do evento, data da última coleta, link verificável, método (quando cálculo agregado).

### `AIExplanation`
Label explícito `Explicação gerada por IA`, data, fonte(s) utilizadas, aviso para consultar texto oficial. Nunca apresentar inferências como fatos.

## Evitar ambiguidades
Não confundir `casa de origem`, `casa em tramitação`, `comissão`, `sessão`, `votação` e `proposição`. Não confundir votos “Sim”, “Não”, “Abstenção”, “Obstrução”, “Ausente” e “Não registrado”; usar classificação exata da fonte e documentar transformações.
