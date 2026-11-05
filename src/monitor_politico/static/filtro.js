(function () {
  var nome = document.getElementById("f-nome");
  var partido = document.getElementById("f-partido");
  var uf = document.getElementById("f-uf");
  var itens = Array.prototype.slice.call(document.querySelectorAll("#lista > li"));
  var contagem = document.getElementById("contagem");
  var vazio = document.getElementById("vazio");

  function normalizar(s) {
    return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  }

  itens.forEach(function (li) { li.dataset.busca = normalizar(li.dataset.nome); });

  function aplicar() {
    var termo = normalizar(nome.value);
    var visiveis = 0;
    itens.forEach(function (li) {
      var ok = (!termo || li.dataset.busca.indexOf(termo) !== -1) &&
        (!partido.value || li.dataset.partido === partido.value) &&
        (!uf.value || li.dataset.uf === uf.value);
      li.hidden = !ok;
      if (ok) visiveis++;
    });
    contagem.textContent = visiveis;
    vazio.hidden = visiveis !== 0;
  }

  [nome, partido, uf].forEach(function (el) { el.addEventListener("input", aplicar); });

  // Botões do resumo (partido, estado): aplicam o filtro e levam à lista; clicar de novo limpa.
  var titulo = document.getElementById("lista-titulo");
  [["data-filtro-partido", partido], ["data-filtro-uf", uf]].forEach(function (par) {
    Array.prototype.forEach.call(document.querySelectorAll("[" + par[0] + "]"), function (botao) {
      botao.addEventListener("click", function () {
        var valor = botao.getAttribute(par[0]);
        par[1].value = par[1].value === valor ? "" : valor;
        aplicar();
        if (titulo) titulo.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
      });
    });
  });

  // Ordenação pelas leis: empate fica na ordem alfabética, que é a ordem original da página.
  var ordem = document.getElementById("f-ordem");
  if (ordem) {
    var lista = document.getElementById("lista");
    itens.forEach(function (li, i) { li.dataset.posicao = i; });
    ordem.addEventListener("change", function () {
      var campo = ordem.value;
      var outro = campo === "principal" ? "coautoria" : "principal";
      itens.slice().sort(function (a, b) {
        if (campo === "nome") return a.dataset.posicao - b.dataset.posicao;
        return (b.dataset[campo] - a.dataset[campo]) || (b.dataset[outro] - a.dataset[outro]) || (a.dataset.posicao - b.dataset.posicao);
      }).forEach(function (li) { lista.appendChild(li); });
    });
  }

  var limpar = document.querySelector("[data-limpar-filtros]");
  if (limpar) {
    limpar.addEventListener("click", function () {
      nome.value = partido.value = uf.value = "";
      aplicar();
      nome.focus();
    });
  }
})();
