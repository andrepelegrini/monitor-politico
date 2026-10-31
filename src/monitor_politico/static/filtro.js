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
})();
