# Arquitetura de informação sugerida

1. **Início**: manchete, agenda desta semana, proposições, votações recentes, última sincronização.
2. **Agenda**: lista temporal com casa/órgão/data/status/links oficiais.
3. **Proposições**: busca, filtros, lista, detalhes com ementa, timeline, documentos, votações relacionadas.
4. **Votações**: histórico, filtros e detalhe de distribuição; registros nominais apenas quando disponíveis.
5. **Parlamentares**: busca, perfil, mandato/legislatura, proposições, comissões e histórico de votos.
6. **Metodologia e fontes**: regras de coleta, atualização, limitações, glossário, critérios de destaque.

## Padrões de navegação
Cada detalhe traz breadcrumb, identificador oficial e links para fonte; cards podem abrir detalhe com URL compartilhável; filtros preservados na URL quando possível; breadcrumbs e voltar não devem perder seleção anterior.

## Semântica de datas
Separe `data_do_evento`, `ultima_atualizacao_da_fonte`, `ultima_sincronizacao_da_plataforma`. Um único timestamp não substitui os três.
