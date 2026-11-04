# Civic Editorial — Design System v1.0

Design system para uma plataforma **neutra de acompanhamento da Câmara dos Deputados e do Senado Federal**. Inspiração estética: editorial minimalista, cores terrosas e tipografia expressiva, reinterpretadas para uma aplicação rica em dados. Não é uma cópia do Linkletter.

## Instalação

1. Copie esta pasta para a raiz do seu repositório (`design-system/` é um bom nome).
2. Abra `examples/index.html` no navegador para ver uma demonstração estática, com **dados fictícios**.
3. Leia `ai/AGENT_INSTRUCTIONS.md` e copie `ai/PROMPT_MIGRATION.md` para sua ferramenta de IA (ou adicione referência no AGENTS.md da raiz do projeto).
4. Integre `tokens/design-tokens.css` **uma vez** no CSS global, depois `components/components.css` (ou mapeie ambos para o sistema de estilos da aplicação).
5. Migre uma rota por vez; preserve toda lógica, API, dados e comportamento existentes.

## Conteúdo

- `tokens/`: CSS custom properties, tipografia, reset e temas.
- `components/`: estilos-base de componentes com classes `ce-*`, framework-agnostic.
- `docs/`: identidade, conteúdo editorial, acessibilidade, visualização de dados, estados, arquitetura, padrões de componentes.
- `templates/`: wireframes textuais para as páginas principais.
- `examples/`: demo HTML estática e acessível, **não conectada a dados reais**.
- `ai/`: contrato e prompts de migração para agentes de IA.

## Princípios inegociáveis

1. **Neutralidade política**. Não atribuir julgamentos de valor a posições, partidos, parlamentares ou resultados. Nunca fazer rankings arbitrários de “bons” e “maus” parlamentares.
2. **Fonte e tempo**. Preservar referência oficial, data do evento e última atualização da coleta em suas respectivas camadas.
3. **Não inventar dados**. Valores e números fictícios devem aparecer somente em ambiente de demonstração, sempre rotulados.
4. **Fidelidade funcional**. Não alterar APIs, contratos, navegação, filtros, ordenações, autenticação, acessibilidade nem regras de negócio durante a reformulação visual.
5. **Densidade disciplinada**. Editorial na apresentação; interface eficiente em tabelas, filtros e exploração.

## Estética principal

- Fundo papel `#FAF8F4`, texto ink `#26221E`, botões espresso `#513C2D`, superfícies `#FFFFFF`, detalhes oliva `#6A7542` e terracota `#B75131`.
- Títulos Fraunces, interface Instrument Sans (fontes obtidas do Google Fonts, com fallback local; não inclua arquivos de fonte sem revisar licenças).
- Bordas finas, sombras raras, muito mais divisórias que cartões; grid máximo 1280px.
- Light mode padrão; modo escuro experimental somente após revisar acessibilidade.

## Checklist inicial

- [ ] Mapear páginas e componentes existentes.
- [ ] Importar tokens e fontes, preservando CSS anterior até a migração terminar.
- [ ] Implementar primitives (botão, input, badge, tabela, cards, loading, vazio, erro).
- [ ] Migrar homepage e validar com dados reais.
- [ ] Migrar pauta, proposição, votação, parlamentar, pesquisa e agenda.
- [ ] Validar keyboard navigation, foco, contraste e responsividade.
- [ ] Comparar antes/depois, validar funcionalidade, executar testes e revisar Git diff.

Este pacote é independente de framework: exemplos em HTML/CSS puro; adapte classes a React, Next, Vue ou outro stack sem reescrever regras de negócio.
