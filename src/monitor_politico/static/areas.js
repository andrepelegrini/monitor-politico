// Página de uma área: filtro por assunto e lista em partes de 20.
// O assunto escolhido fica no endereço (areas/seguranca.html#armas-de-fogo), que é para onde a busca do topo leva.
(function () {
  var lista = document.getElementById("ar-lista");
  if (!lista) return;
  var itens = Array.prototype.slice.call(lista.children);
  var chips = document.getElementById("ar-chips");
  var mais = document.getElementById("ar-mais");
  var titulo = document.getElementById("ar-titulo");
  var conta = document.getElementById("ar-conta");
  var PASSO = 20, limite = PASSO, atual = "";

  function plural(n, um, varios) { return n.toLocaleString("pt-BR") + " " + (n === 1 ? um : varios); }

  function mostrar() {
    var total = 0, leis = 0;
    itens.forEach(function (li) {
      var entra = !atual || li.dataset.assuntos.indexOf("|" + atual + "|") >= 0;
      if (entra) { total++; if (li.dataset.lei === "1") leis++; }
      li.hidden = !entra || total > limite;
    });
    titulo.textContent = atual || titulo.dataset.todos;
    conta.textContent = plural(total, "projeto", "projetos") + ", " + leis.toLocaleString("pt-BR") + (leis === 1 ? " virou lei" : " viraram lei");
    mais.hidden = total <= limite;
    if (chips) Array.prototype.forEach.call(chips.children, function (b) { b.setAttribute("aria-pressed", String(b.dataset.assunto === atual)); });
  }

  function doEndereco() {
    if (!chips) return;
    var slug = decodeURIComponent(location.hash.slice(1));
    var b = chips.querySelector('button[data-slug="' + slug.replace(/[^a-z0-9-]/g, "") + '"]');
    atual = b ? b.dataset.assunto : "";
    limite = PASSO;
  }

  if (chips) {
    chips.hidden = false;
    chips.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      atual = b.dataset.assunto;
      limite = PASSO;
      history.replaceState(null, "", b.dataset.slug ? "#" + b.dataset.slug : location.pathname + location.search);
      mostrar();
    });
    window.addEventListener("hashchange", function () { doEndereco(); mostrar(); });
  }
  mais.addEventListener("click", function () {
    var primeiro = itens.filter(function (li) { return li.hidden && (!atual || li.dataset.assuntos.indexOf("|" + atual + "|") >= 0); })[0];
    limite += PASSO;
    mostrar();
    if (primeiro) { var a = primeiro.querySelector("a"); if (a) a.focus(); }
  });
  doEndereco();
  mostrar();
})();
