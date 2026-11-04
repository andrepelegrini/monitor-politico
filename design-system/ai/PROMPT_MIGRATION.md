# Prompt para colar no seu agente de código

Quero migrar o frontend existente deste repositório para o design system **Civic Editorial** que está na pasta `design-system/`.

Leia por completo `design-system/README.md`, `design-system/ai/AGENT_INSTRUCTIONS.md`, todos os arquivos de `design-system/docs/`, os tokens, os componentes e os templates.

**Não recrie a aplicação do zero.** Antes de alterar qualquer arquivo, inspecione o projeto real e enumere rotas, componentes, stack, CSS vigente, integrações e riscos. Use o framework e convenções já adotados.

Implemente o design system com as cores, tipografia, escala, layout e linguagem editorial indicados. Integre `tokens/design-tokens.css`, `tokens/base.css`, e `components/components.css` (ou mapeie-os para os componentes nativos do stack). Preserve a semântica da aplicação. Use `.ce-app` durante a migração para isolar estilos.

Migre nesta ordem: (1) estrutura global e navegação; (2) homepage; (3) componentes base; (4) proposições; (5) votações; (6) parlamentares; (7) agenda e busca; (8) estados de carregamento/erro/vazio e QA.

Todos os dados devem continuar vindo das fontes existentes. NUNCA use valores fictícios presentes nos exemplos HTML em produção. Preserve contratos de API, URLs, filtros, autenticação, dados e lógica de negócio. Não introduza ranking político nem sinalização de bom/ruim por cor. Diferencie datas de evento e sincronização e apresente fontes quando disponíveis.

Verifique desktop, tablet, mobile, foco de teclado, contraste e acessibilidade WCAG 2.2 AA. Rode os testes/build existentes. Ao concluir, informe arquivos alterados, validações executadas e pendências, incluindo eventuais dados de origem não disponíveis.
