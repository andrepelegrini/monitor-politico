# Estados de interface

| Estado | Mensagem | Comportamento |
|---|---|---|
| Loading | Carregando votações… | skeleton discreto, sem piscar; aria-busy |
| Empty real | Nenhum resultado para estes filtros | botão limpar filtros e contexto de busca |
| Missing | Dado não disponível na fonte consultada | não inferir zero nem ausência |
| Error | Não foi possível carregar os dados | tentar novamente, manter contexto |
| Stale | Última atualização em … | datar e preservar dados com aviso explícito |
| Planned | Previsto na agenda | diferenciar de realizado |
| Cancelled | Evento cancelado conforme fonte | mostrar data de atualização |
| AI | Explicação gerada por IA | separar texto oficial e resumo |

Evitar cor isolada como sinal. Use texto e ícones complementares. Em atualizações dinâmicas, anúncios `aria-live=polite` sem excesso.
