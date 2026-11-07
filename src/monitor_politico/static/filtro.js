(function () {
  var nome = document.getElementById("f-nome");
  var partido = document.getElementById("f-partido");
  var uf = document.getElementById("f-uf");
  var situacao = document.getElementById("f-situacao");
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
        (!uf.value || li.dataset.uf === uf.value) &&
        (!situacao || !situacao.value || (li.dataset.situacao || "").indexOf(situacao.value) === 0);
      li.hidden = !ok;
      if (ok) visiveis++;
    });
    contagem.textContent = visiveis;
    vazio.hidden = visiveis !== 0;
    marcarEstado();
  }

  // Mapa das bancadas: destaca o estado filtrado, venha o filtro do mapa, da lista ou do campo UF.
  function marcarEstado() {
    var formas = document.querySelectorAll(".mapa-uf");
    if (!formas.length) return;
    var escolhida = null;
    Array.prototype.forEach.call(formas, function (forma) {
      var ativa = forma.getAttribute("data-filtro-uf") === uf.value;
      forma.setAttribute("aria-pressed", String(ativa));
      if (ativa) escolhida = forma;
    });
    document.getElementById("mapa-vazio").hidden = !!escolhida;
    document.getElementById("mapa-estado").hidden = !escolhida;
    if (escolhida) {
      document.getElementById("mapa-nome").textContent = escolhida.getAttribute("data-nome");
      document.getElementById("mapa-n").textContent = escolhida.getAttribute("data-n");
      document.getElementById("mapa-maior").textContent = escolhida.getAttribute("data-maior");
      escolhida.parentNode.appendChild(escolhida);  // contorno de destaque por cima dos vizinhos
    }
  }

  [nome, partido, uf, situacao].forEach(function (el) { if (el) el.addEventListener("input", aplicar); });

  // Estados do mapa são formas do SVG, e não botões: Enter e espaço também os acionam.
  Array.prototype.forEach.call(document.querySelectorAll(".mapa-uf"), function (forma) {
    forma.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter" || evento.key === " ") {
        evento.preventDefault();
        forma.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      }
    });
  });

  // Botões do resumo (partido, estado): aplicam o filtro e levam à lista; clicar de novo limpa.
  var titulo = document.getElementById("lista-titulo");
  [["data-filtro-partido", partido], ["data-filtro-uf", uf]].forEach(function (par) {
    Array.prototype.forEach.call(document.querySelectorAll("[" + par[0] + "]"), function (botao) {
      botao.addEventListener("click", function () {
        var valor = botao.getAttribute(par[0]);
        par[1].value = par[1].value === valor ? "" : valor;
        aplicar();
        // No mapa, o estado escolhido fica no mapa: sem rolar até a lista, o painel ao lado mostra o resultado.
        if (botao.classList.contains("mapa-uf")) return;
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
      var desempate = campo === "coautoria" ? "principal" : "coautoria";
      itens.slice().sort(function (a, b) {
        if (campo === "nome") return a.dataset.posicao - b.dataset.posicao;
        return (b.dataset[campo] - a.dataset[campo]) || (b.dataset[desempate] - a.dataset[desempate]) || (a.dataset.posicao - b.dataset.posicao);
      }).forEach(function (li) { lista.appendChild(li); });
    });
  }

  var limpar = document.querySelector("[data-limpar-filtros]");
  if (limpar) {
    limpar.addEventListener("click", function () {
      nome.value = partido.value = uf.value = "";
      if (situacao) situacao.value = "";
      aplicar();
      nome.focus();
    });
  }
})();
