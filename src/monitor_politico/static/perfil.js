// Filtros e paginação das listas do perfil do parlamentar (votações e propostas).
// Sem JavaScript, todos os itens ficam visíveis.
function listaFiltravel(prefixo, controles, passa, padroes) {
  var lista = document.getElementById(prefixo + "-lista");
  if (!lista) return;

  var POR_VEZ = 15;
  var itens = Array.prototype.slice.call(lista.children);
  var contagem = document.getElementById(prefixo + "-contagem");
  var vazio = document.getElementById(prefixo + "-vazio");
  var mais = document.getElementById(prefixo + "-mais");
  var campos = {};
  controles.forEach(function (nome) { campos[nome] = document.getElementById(prefixo + "-" + nome); });
  var limite = POR_VEZ;

  function aplicar() {
    var total = 0;
    itens.forEach(function (li) {
      var ok = passa(li, campos);
      if (ok) total++;
      li.hidden = !ok || total > limite;
    });
    contagem.textContent = total.toLocaleString("pt-BR");
    vazio.hidden = total !== 0;
    mais.hidden = total <= limite;
  }

  controles.forEach(function (nome) {
    campos[nome].addEventListener("change", function () {
      limite = POR_VEZ;
      aplicar();
    });
  });

  mais.addEventListener("click", function () {
    // Leva o foco para o primeiro item novo, para quem navega pelo teclado não voltar ao topo da lista.
    var ocultos = itens.filter(function (li) { return li.hidden && passa(li, campos); });
    limite += POR_VEZ;
    aplicar();
    var primeiro = ocultos[0] && ocultos[0].querySelector("a");
    if (primeiro) primeiro.focus();
  });

  document.getElementById(prefixo + "-limpar").addEventListener("click", function () {
    controles.forEach(function (nome) {
      var campo = campos[nome];
      if (campo.type === "checkbox") campo.checked = false;
      else campo.value = (padroes && padroes[nome]) || "";
    });
    limite = POR_VEZ;
    aplicar();
    campos[controles[0]].focus();
  });

  aplicar();
}

listaFiltravel("v", ["classe", "tema", "voto", "contra", "difere"], function (li, c) {
  return (!c.classe.value || li.dataset.classe === c.classe.value) &&
    (!c.tema.value || li.dataset.temas.split("|").indexOf(c.tema.value) !== -1) &&
    (!c.voto.value || li.dataset.voto === c.voto.value) &&
    (!c.contra.checked || li.dataset.contra === "1") &&
    (!c.difere.checked || li.dataset.difere === "1");
}, { classe: "texto" });

listaFiltravel("p", ["participacao", "situacao", "mandato", "tema", "tipo"], function (li, c) {
  return (!c.tipo.value || li.dataset.tipo === c.tipo.value) &&
    (!c.mandato.value || li.dataset.mandato === c.mandato.value) &&
    (!c.tema.value || li.dataset.temas.split("|").indexOf(c.tema.value) !== -1) &&
    (!c.participacao.value || li.dataset.participacao === c.participacao.value) &&
    (!c.situacao.value || li.dataset.situacao === c.situacao.value);
});

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

// Compartilhar o perfil. Sem JavaScript, os botões não aparecem.
(function () {
  var caixa = document.getElementById("compartilhar");
  if (!caixa) return;

  var endereco = location.origin + location.pathname;
  var texto = caixa.dataset.texto;
  var aviso = document.getElementById("s-aviso");
  var nativo = document.getElementById("s-nativo");

  document.getElementById("s-whatsapp").href = "https://wa.me/?text=" + encodeURIComponent(texto + " " + endereco);

  document.getElementById("s-copiar").addEventListener("click", function () {
    function falhou() { aviso.textContent = "Não foi possível copiar. Endereço: " + endereco; }
    if (!navigator.clipboard) return falhou();
    navigator.clipboard.writeText(endereco).then(function () { aviso.textContent = "Link copiado."; }, falhou);
  });

  if (navigator.share) {
    nativo.hidden = false;
    nativo.addEventListener("click", function () {
      navigator.share({ title: document.title, text: texto, url: endereco }).catch(function () {});
    });
  }
  caixa.hidden = false;
})();

// Marca na navegação do perfil a seção que está na tela.
(function () {
  var navegacao = document.querySelector(".pf-ancoras");
  if (!navegacao || !("IntersectionObserver" in window)) return;

  var links = Array.prototype.slice.call(navegacao.querySelectorAll("a"));
  var porSecao = {};
  links.forEach(function (link) { porSecao[link.getAttribute("href").slice(1)] = link; });

  function marcar(atual) {
    links.forEach(function (link) { link.removeAttribute("aria-current"); });
    atual.setAttribute("aria-current", "true");
    navegacao.scrollLeft = atual.offsetLeft - navegacao.offsetLeft - 16;
  }

  var observador = new IntersectionObserver(function (entradas) {
    entradas.forEach(function (entrada) {
      if (entrada.isIntersecting) marcar(porSecao[entrada.target.id]);
    });
  }, { rootMargin: "-20% 0px -70% 0px" });

  // A última seção é curta e pode nunca chegar à faixa observada: no fim da página, ela é a atual.
  window.addEventListener("scroll", function () {
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 8) marcar(links[links.length - 1]);
  }, { passive: true });

  Object.keys(porSecao).forEach(function (id) {
    var secao = document.getElementById(id);
    if (secao) observador.observe(secao);
  });
})();
