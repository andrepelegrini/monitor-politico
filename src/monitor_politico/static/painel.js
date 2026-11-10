(function () {
  function normalizar(s) {
    return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  }

  function rolagem() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  }

  // Página principal: filtros das votações recentes e chips de tema.
  var lista = document.getElementById("lista-votadas");
  if (lista) {
    var casa = document.getElementById("f-casa");
    var tema = document.getElementById("f-tema");
    var resultado = document.getElementById("f-resultado");
    var nominal = document.getElementById("f-nominal");
    var itens = Array.prototype.slice.call(lista.children);
    var contagem = document.getElementById("contagem");
    var vazio = document.getElementById("vazio");

    var aplicar = function () {
      var visiveis = 0;
      itens.forEach(function (li) {
        var ok = (!casa.value || li.dataset.casas.split("|").indexOf(casa.value) !== -1) &&
          (!tema.value || li.dataset.temas.indexOf("|" + tema.value + "|") !== -1) &&
          (!resultado.value || li.dataset.resultados.split("|").indexOf(resultado.value) !== -1) &&
          (!nominal.checked || li.dataset.nominal === "1");
        li.hidden = !ok;
        if (ok) visiveis++;
      });
      contagem.textContent = visiveis;
      vazio.hidden = visiveis !== 0;
    };
    [casa, tema, resultado, nominal].forEach(function (el) { el.addEventListener("input", aplicar); });

    // Vindo de "Assuntos do mês" na página inicial: votacoes.html?tema=Saúde já abre filtrada.
    var temaPedido = new URLSearchParams(location.search).get("tema");
    if (temaPedido && Array.prototype.some.call(tema.options, function (o) { return o.value === temaPedido; })) {
      tema.value = temaPedido;
      aplicar();
    }

    Array.prototype.forEach.call(document.querySelectorAll(".chip[data-tema]"), function (chip) {
      chip.addEventListener("click", function () {
        tema.value = tema.value === chip.dataset.tema ? "" : chip.dataset.tema;
        aplicar();
        document.getElementById("votadas").scrollIntoView({ behavior: rolagem() });
      });
    });

    Array.prototype.forEach.call(document.querySelectorAll("[data-limpar-filtros]"), function (botao) {
      botao.addEventListener("click", function () {
        casa.value = tema.value = resultado.value = "";
        nominal.checked = false;
        aplicar();
        casa.focus();
      });
    });
  }

  // Página da proposição: abas das votações nominais e filtros da tabela de votos.
  var abas = Array.prototype.slice.call(document.querySelectorAll('.abas [role="tab"]'));
  var selecionar = function (aba) {
    abas.forEach(function (a) {
      var ativa = a === aba;
      a.setAttribute("aria-selected", ativa ? "true" : "false");
      a.tabIndex = ativa ? 0 : -1;
      document.getElementById(a.getAttribute("aria-controls")).hidden = !ativa;
    });
  };
  abas.forEach(function (aba, i) {
    aba.addEventListener("click", function () { selecionar(aba); });
    aba.addEventListener("keydown", function (e) {
      var alvo = e.key === "ArrowRight" ? abas[(i + 1) % abas.length] : e.key === "ArrowLeft" ? abas[(i - 1 + abas.length) % abas.length] : null;
      if (alvo) { selecionar(alvo); alvo.focus(); e.preventDefault(); }
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll(".painel-votos"), function (painel) {
    var nome = painel.querySelector(".v-nome");
    var partido = painel.querySelector(".v-partido");
    var uf = painel.querySelector(".v-uf");
    var voto = painel.querySelector(".v-voto");
    var linhas = Array.prototype.slice.call(painel.querySelectorAll("tbody tr"));
    var contagem = painel.querySelector(".v-contagem");
    var tabela = painel.querySelector(".ce-table-scroll");
    var vazio = painel.querySelector(".v-vazio");
    linhas.forEach(function (tr) { tr.dataset.busca = normalizar(tr.dataset.nome); });

    var aplicar = function () {
      var termo = normalizar(nome.value);
      var visiveis = 0;
      linhas.forEach(function (tr) {
        var ok = (!termo || tr.dataset.busca.indexOf(termo) !== -1) &&
          (!partido.value || tr.dataset.partido === partido.value) &&
          (!uf.value || tr.dataset.uf === uf.value) &&
          (!voto.value || tr.dataset.voto === voto.value);
        tr.hidden = !ok;
        if (ok) visiveis++;
      });
      contagem.textContent = visiveis;
      tabela.hidden = visiveis === 0;
      vazio.hidden = visiveis !== 0;
    };
    [nome, partido, uf, voto].forEach(function (el) { el.addEventListener("input", aplicar); });
    painel.querySelector(".v-limpar").addEventListener("click", function () {
      nome.value = partido.value = uf.value = voto.value = "";
      aplicar();
      nome.focus();
    });
  });
})();
