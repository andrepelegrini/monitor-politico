// Filtros e paginação das votações no perfil do parlamentar.
// Sem JavaScript, todas as votações ficam visíveis.
(function () {
  var lista = document.getElementById("v-lista");
  if (!lista) return;

  var POR_VEZ = 15;
  var itens = Array.prototype.slice.call(lista.children);
  var classe = document.getElementById("v-classe");
  var tema = document.getElementById("v-tema");
  var voto = document.getElementById("v-voto");
  var contra = document.getElementById("v-contra");
  var difere = document.getElementById("v-difere");
  var contagem = document.getElementById("v-contagem");
  var vazio = document.getElementById("v-vazio");
  var mais = document.getElementById("v-mais");
  var limite = POR_VEZ;

  function passa(li) {
    return (!classe.value || li.dataset.classe === classe.value) &&
      (!tema.value || li.dataset.temas.split("|").indexOf(tema.value) !== -1) &&
      (!voto.value || li.dataset.voto === voto.value) &&
      (!contra.checked || li.dataset.contra === "1") &&
      (!difere.checked || li.dataset.difere === "1");
  }

  function aplicar() {
    var total = 0;
    itens.forEach(function (li) {
      var ok = passa(li);
      if (ok) total++;
      li.hidden = !ok || total > limite;
    });
    contagem.textContent = total.toLocaleString("pt-BR");
    vazio.hidden = total !== 0;
    mais.hidden = total <= limite;
  }

  [classe, tema, voto, contra, difere].forEach(function (controle) {
    controle.addEventListener("change", function () {
      limite = POR_VEZ;
      aplicar();
    });
  });

  mais.addEventListener("click", function () {
    // Leva o foco para a primeira votação nova, para quem navega pelo teclado não voltar ao topo da lista.
    var ocultos = itens.filter(function (li) { return li.hidden && passa(li); });
    limite += POR_VEZ;
    aplicar();
    var primeiro = ocultos[0] && ocultos[0].querySelector("a");
    if (primeiro) primeiro.focus();
  });

  document.getElementById("v-limpar").addEventListener("click", function () {
    classe.value = "texto";
    tema.value = voto.value = "";
    contra.checked = difere.checked = false;
    limite = POR_VEZ;
    aplicar();
    classe.focus();
  });

  aplicar();
})();

// Comprovantes da cota: a lista completa só é baixada quando alguém vai usá-la.
// Sem JavaScript, ficam os maiores comprovantes, que já vêm na página.
(function () {
  var filtros = document.getElementById("c-filtros");
  if (!filtros) return;

  var POR_VEZ = 20;
  var ORIGEM_DOCUMENTOS = "https://www.camara.leg.br/";
  var busca = document.getElementById("c-busca");
  var categoria = document.getElementById("c-categoria");
  var corpo = document.getElementById("c-lista");
  var contagem = document.getElementById("c-contagem");
  var mais = document.getElementById("c-mais");
  var todos = null;
  var pedido = null;
  var limite = POR_VEZ;

  function normalizar(s) {
    return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  function moeda(v) {
    return "R$ " + v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function celula(linha, texto, classe) {
    var td = linha.insertCell();
    td.textContent = texto;
    if (classe) td.className = classe;
    return td;
  }

  function desenhar() {
    var termo = normalizar(busca.value.trim());
    var lista = todos.filter(function (c) {
      return (!categoria.value || c.categoria === categoria.value) && (!termo || normalizar(c.fornecedor).indexOf(termo) !== -1);
    });
    var soma = lista.reduce(function (t, c) { return t + c.valor; }, 0);
    contagem.textContent = lista.length.toLocaleString("pt-BR") + (lista.length === 1 ? " comprovante, somando " : " comprovantes, somando ") + moeda(soma) + ". Maiores valores primeiro.";
    corpo.textContent = "";
    lista.slice(0, limite).forEach(function (c) {
      var linha = corpo.insertRow();
      celula(linha, c.mes.slice(5) + "/" + c.mes.slice(0, 4));
      celula(linha, c.fornecedor);
      celula(linha, c.categoria);
      celula(linha, moeda(c.valor), "pf-num");
      var documento = linha.insertCell();
      if (c.url && c.url.indexOf(ORIGEM_DOCUMENTOS) === 0) {
        var link = document.createElement("a");
        link.href = c.url;
        link.textContent = "Abrir";
        documento.appendChild(link);
      } else {
        documento.textContent = "Sem arquivo";
      }
    });
    mais.hidden = lista.length <= limite;
  }

  function carregar() {
    if (!pedido) {
      pedido = fetch(filtros.dataset.url)
        .then(function (r) {
          if (!r.ok) throw new Error(String(r.status));
          return r.json();
        })
        .then(function (dados) { todos = dados; })
        .catch(function () {
          pedido = null;
          contagem.textContent = "Não foi possível carregar a lista completa. Tente novamente.";
          throw new Error("comprovantes indisponíveis");
        });
    }
    return pedido;
  }

  function aplicar() {
    limite = POR_VEZ;
    carregar().then(desenhar).catch(function () {});
  }

  busca.addEventListener("input", aplicar);
  categoria.addEventListener("change", aplicar);
  mais.addEventListener("click", function () {
    var primeiraNova = corpo.rows.length;
    carregar().then(function () {
      limite = Math.max(limite, primeiraNova) + POR_VEZ;
      desenhar();
      var link = corpo.rows[primeiraNova] && corpo.rows[primeiraNova].querySelector("a");
      if (link) link.focus();
    }).catch(function () {});
  });

  // Os controles só aparecem com JavaScript.
  filtros.hidden = false;
  mais.hidden = false;
})();
