# Contrato para agentes de IA

**Este arquivo é normativo para qualquer redesign.** Consulte `README.md`, `tokens/`, `docs/` e `templates/` antes de implementar.

## Prioridades
1. Preservar funcionamento, acessibilidade, APIs, banco, rotas, permissões, analytics e performance.
2. Adotar tokens e componentes e eliminar estilo ad hoc **apenas** das páginas migradas.
3. Preservar neutralidade, procedência e granularidade dos dados oficiais.

## Processo obrigatório
1. Inventariar stack, rotas e estilos existentes; identificar pontos de conflito CSS.
2. Propor plano de migração por etapas com arquivos afetados e riscos; não reescrever tudo cegamente.
3. Implementar tokens centralizados com escopo `.ce-app` para evitar regressões no legado.
4. Fazer homepage como piloto e inspecionar UI desktop e mobile.
5. Extrair componentes compartilhados; migrar detalhe de proposição, votação, parlamentar, agenda e pesquisa.
6. Auditar contraste, teclado, texto alternativo, responsividade, vazios/erros/atrasos.
7. Executar testes, build e validações existentes; relatar modificações e pendências.

## Nunca
- Inventar dados, timestamps, URLs oficiais, parlamentares, votos ou atividades legislativas.
- Alterar resultados, lógica de consulta/filtragem ou tipagem dos dados em nome do design.
- Usar verde/vermellho como avaliação de votos Sim/Não.
- Substituir votação nominal por simbólica ou deduzir comportamento de ausência de registro.
- Usar emojis em UI de produção; usar ícones consistentes.
- Adicionar dependências e fontes proprietárias sem justificativa/licença.

## Critérios de aceite
Sem regressão de funções, sem overflow horizontal geral em 375px, sem contraste insuficiente, todos elementos interativos alcançáveis por teclado, páginas importantes com fonte/data, sem hardcoded placeholders de demo, build e testes passando.
