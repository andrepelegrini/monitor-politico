// Página do estado: busca por nome, ordenação pelos números do mandato e "Mostrar todos".
// Sem JavaScript, aparecem os primeiros deputados em ordem alfabética.
(function () {
  var lista = document.getElementById("e-lista");
  if (!lista) return;
  var nome = document.getElementById("e-nome");
  var ordem = document.getElementById("e-ordem");
  var mais = document.getElementById("e-mais");
  var vazio = document.getElementById("e-vazio");
  var limite = Number(lista.dataset.naPagina) || 12;
  var abertos = false;
  var itens = Array.prototype.slice.call(lista.children);
  itens.forEach(function (li, i) { li.dataset.posicao = i; });

  function normalizar(s) {
    return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  }

  function aplicar() {
    var termo = normalizar(nome.value);
    var campo = ordem ? ordem.value : "nome";
    itens.slice().sort(function (a, b) {
      if (campo === "nome") return a.dataset.posicao - b.dataset.posicao;
      return (b.dataset[campo] - a.dataset[campo]) || (a.dataset.posicao - b.dataset.posicao);
    }).forEach(function (li) { lista.appendChild(li); });
    var visiveis = 0;
    Array.prototype.forEach.call(lista.children, function (li) {
      var ok = !termo || normalizar(li.dataset.nome).indexOf(termo) !== -1;
      if (ok) visiveis++;
      li.hidden = !ok || (!abertos && !termo && visiveis > limite);
    });
    vazio.hidden = visiveis !== 0;
    if (mais) mais.hidden = abertos || !!termo;
  }

  nome.addEventListener("input", aplicar);
  if (ordem) ordem.addEventListener("change", aplicar);
  if (mais) {
    mais.addEventListener("click", function () {
      abertos = true;
      aplicar();
      // Leva o foco para o primeiro deputado que acabou de aparecer.
      var novo = lista.children[limite] && lista.children[limite].querySelector("a");
      if (novo) novo.focus();
    });
  }
})();
