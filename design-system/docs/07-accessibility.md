# Acessibilidade — objetivo WCAG 2.2 AA

- Contraste mínimo: texto comum 4.5:1; texto grande 3:1; elementos não textuais 3:1 onde aplicável. Testar combinações reais, não apenas hex isolados.
- Cor nunca é a única maneira de transmitir voto, status ou erro.
- Foco visível; fluxo sem teclado-traps; skip link; landmarks main/nav/header/footer.
- Controles com label; botão ícone precisa de nome acessível; erros associados ao input.
- Tabelas: `caption`, `th scope`, `aria-sort` para ordem, títulos legíveis, rolagem horizontal com contexto.
- Gráficos com equivalente tabular ou textual e explicação do denominador.
- Datas com formato explícito e fuso horário (por padrão Brasília quando aplicável).
- `prefers-reduced-motion`: reduzir ou eliminar movimentos.
- Zoom 200–400%, largura estreita, fontes ampliadas, dark mode se existir.
- Revisão automatizada (axe/Lighthouse) **e manual** em teclado e leitor de tela.
