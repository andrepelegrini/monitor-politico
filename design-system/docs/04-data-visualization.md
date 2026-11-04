# Visualização e tratamento de votos

## Regra de neutralidade
NÃO usar verde de sucesso para Sim ou vermelho de erro para Não. Votos são **categorias**, não resultados positivos/negativos.

Mapeamento de cores acessório (não único identificador):
- Sim `--ce-vote-yes` #356BB3
- Não `--ce-vote-no` #A66B16
- Abstenção `--ce-vote-abstention` #697788
- Outras classificações `--ce-vote-other` #8B7F73 com legenda específica

Oliva e terracota permanecem acentos de marca, NÃO marcadores morais. Nunca deixar de incluir rótulo legível e contagem.

## Charts
- Barra empilhada para distribuição, gráfico temporal apenas quando fonte e períodos comparáveis.
- Exibir contagens e denominador da votação em texto; percentuais são complementares.
- Anotar votações simbólicas e resultados sem registros nominais.
- Cuidado com totais que não somam número total de membros; faltas, licenças e participações têm definições distintas.
- Não usar pizza com muitas categorias; preferir barras e tabelas.
- Tooltip não pode ser o único lugar com dados essenciais; suporte a teclado e tabela equivalente.
- Partidos e parlamentares não recebem cores que impliquem aprovação, desaprovação ou nota.

## Seleção de destaque
Ordenar por data, agenda oficial ou filtros explicitados. Se houver destaque editorial, divulgar critérios objetivos e permitir explorar a lista completa. Evitar inferir relevância política a partir de algoritmo opaco.
