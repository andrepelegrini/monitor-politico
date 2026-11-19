// Lista de parlamentares: marcar até três para comparar lado a lado.
(function () {
  var barra = document.getElementById("cmp-barra");
  if (!barra) return;
  var MAX = 3;
  var caixas = Array.prototype.slice.call(document.querySelectorAll(".cmp-marca input"));
  var texto = document.getElementById("cmp-barra-texto");
  var ir = document.getElementById("cmp-barra-ir");
  var escolhidos = [];

  function atualizar() {
    var n = escolhidos.length;
    caixas.forEach(function (c) { c.disabled = !c.checked && n >= MAX; });
    barra.hidden = n === 0;
    texto.textContent = n === 1 ? "1 pessoa escolhida. Marque mais uma ou duas." : n + " pessoas escolhidas" + (n >= MAX ? " (máximo)" : "");
    ir.href = "comparar.html" + (n ? "#" + escolhidos.join("-") : "");
    if (n < 2) ir.setAttribute("aria-disabled", "true"); else ir.removeAttribute("aria-disabled");
  }

  caixas.forEach(function (c) {
    c.parentNode.hidden = false;
    c.checked = false;
    c.addEventListener("change", function () {
      if (c.checked) escolhidos.push(c.value);
      else escolhidos = escolhidos.filter(function (id) { return id !== c.value; });
      atualizar();
    });
  });
  document.getElementById("cmp-barra-limpar").addEventListener("click", function () {
    caixas.forEach(function (c) { c.checked = false; });
    escolhidos = [];
    atualizar();
  });
})();
