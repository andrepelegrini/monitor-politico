// Busca única no topo: assuntos, parlamentares das duas Casas e proposições do período.
// O índice (static/busca.json) é gerado no build e só é baixado quando a pessoa usa a busca.
(function () {
  var caixa = document.getElementById("busca");
  if (!caixa) return;
  var q = document.getElementById("busca-q");
  var res = document.getElementById("busca-res");
  var raiz = caixa.dataset.raiz || ".";
  var indice = null, carregando = null, sel = -1;
  var MAX_PESSOAS = 7, MAX_PROPS = 4, MAX_ASSUNTOS = 3;

  function norm(s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function carregar() {
    if (!carregando) {
      carregando = fetch(raiz + "/static/busca.json")
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (d) {
          indice = {
            pessoas: d.parlamentares.map(function (p) {
              return { nome: p[0], casa: p[1], partido: p[2], uf: p[3], url: p[4], nn: norm(p[0]), chave: norm(p[0] + " " + p[2] + " " + p[3]) };
            }),
            props: d.proposicoes.map(function (p) {
              return { chave: p[0], titulo: p[1], url: p[2], busca: norm(p[0] + " " + p[0].replace(/[ /]/g, "") + " " + p[1]) };
            }),
            // Assuntos casam por início de palavra: "arma" acha "Armas de fogo", mas "ir" não acha "Moradia".
            assuntos: (d.assuntos || []).map(function (a) {
              return { nome: a[0], area: a[1], url: a[2], total: a[3], nn: norm(a[0]), doNome: norm(a[0]).split(/[^a-z0-9]+/), palavras: norm(a[0] + " " + a[1] + " " + a[4]).split(/[^a-z0-9]+/) };
            })
          };
        })
        .catch(function () { carregando = null; });
    }
    return carregando;
  }

  function destacar(nome, termo) {
    var i = norm(nome).indexOf(termo);
    if (!termo || i < 0) return esc(nome);
    return esc(nome.slice(0, i)) + "<mark>" + esc(nome.slice(i, i + termo.length)) + "</mark>" + esc(nome.slice(i + termo.length));
  }
  function iniciais(n) { var p = n.split(" "); return (p[0][0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase(); }
  function contem(texto, palavras) { return palavras.every(function (w) { return texto.indexOf(w) !== -1; }); }
  function comeca(lista, palavras) {
    return palavras.every(function (w) { return lista.some(function (t) { return t.indexOf(w) === 0; }); });
  }
  function projetos(n) { return n.toLocaleString("pt-BR") + (n === 1 ? " projeto votado" : " projetos votados"); }

  function fechar() { res.hidden = true; q.setAttribute("aria-expanded", "false"); q.removeAttribute("aria-activedescendant"); sel = -1; }
  function abrir(html) { res.innerHTML = html; res.hidden = false; q.setAttribute("aria-expanded", "true"); sel = -1; }

  function render() {
    var bruto = q.value.trim(), termo = norm(bruto);
    if (termo.length < 2) { fechar(); return; }
    if (!indice) {
      abrir('<li class="aviso">Carregando…</li>');
      carregar().then(function () {
        if (indice) render();
        else abrir('<li class="aviso">Não foi possível carregar a busca. Recarregue a página e tente de novo.</li>');
      });
      return;
    }
    var pal = termo.split(/\s+/);
    var pessoas = indice.pessoas.filter(function (p) { return contem(p.chave, pal); }).sort(function (a, b) {
      return (a.nn.indexOf(termo) === 0 ? 0 : 1) - (b.nn.indexOf(termo) === 0 ? 0 : 1);
    });
    var props = indice.props.filter(function (p) { return contem(p.busca, pal); });
    // Primeiro quem começa com o termo, depois quem tem a palavra no nome, depois quem só a tem nas palavras extras.
    function ordem(a) { return a.nn.indexOf(termo) === 0 ? 0 : comeca(a.doNome, pal) ? 1 : 2; }
    var assuntos = indice.assuntos.filter(function (a) { return comeca(a.palavras, pal); }).sort(function (a, b) {
      return ordem(a) - ordem(b) || b.total - a.total;
    });
    var html = "", n = 0;
    if (assuntos.length) {
      html += '<li class="grupo" role="presentation">Assuntos · ' + assuntos.length + "</li>";
      assuntos.slice(0, MAX_ASSUNTOS).forEach(function (a) {
        html += '<li role="presentation"><a id="busca-op-' + (n++) + '" role="option" href="' + raiz + "/" + a.url + '"><span class="av tema" aria-hidden="true">#</span><span><span class="n">' +
          destacar(a.nome, pal[0]) + '</span><span class="m">' + (a.area ? "Assunto em " + esc(a.area) : "Área") + " · " + projetos(a.total) + "</span></span></a></li>";
      });
    }
    if (pessoas.length) {
      html += '<li class="grupo" role="presentation">Parlamentares · ' + pessoas.length + "</li>";
      pessoas.slice(0, MAX_PESSOAS).forEach(function (p) {
        html += '<li role="presentation"><a id="busca-op-' + (n++) + '" role="option" href="' + raiz + "/" + p.url + '"><span class="av" aria-hidden="true">' + iniciais(p.nome) +
          '</span><span><span class="n">' + destacar(p.nome, pal[0]) + '</span><span class="m">' + (p.casa === "D" ? "Câmara" : "Senado") +
          " · " + esc(p.partido) + "-" + esc(p.uf) + "</span></span></a></li>";
      });
      if (pessoas.length > MAX_PESSOAS) {
        html += '<li class="mais" role="presentation">Mais ' + (pessoas.length - MAX_PESSOAS) + " parlamentares. Refine com partido ou UF, por exemplo “" + esc(bruto) + ' sp”.</li>';
      }
    }
    if (props.length) {
      html += '<li class="grupo" role="presentation">Proposições · ' + props.length + "</li>";
      props.slice(0, MAX_PROPS).forEach(function (p) {
        html += '<li role="presentation"><a id="busca-op-' + (n++) + '" role="option" href="' + raiz + "/" + p.url + '"><span class="av prop" aria-hidden="true">' + esc(p.chave.split(" ")[0]) +
          '</span><span><span class="n">' + esc(p.chave) + '</span><span class="m">' + esc(p.titulo) + "</span></span></a></li>";
      });
    }
    abrir(html || '<li class="aviso">Nenhum parlamentar, proposição ou assunto encontrado para “' + esc(bruto) + "”.</li>");
  }

  function mover(d) {
    var ops = res.querySelectorAll("a[role=option]");
    if (!ops.length) return;
    if (sel >= 0) ops[sel].removeAttribute("aria-selected");
    sel = (sel + d + ops.length) % ops.length;
    ops[sel].setAttribute("aria-selected", "true");
    q.setAttribute("aria-activedescendant", ops[sel].id);
    ops[sel].scrollIntoView({ block: "nearest" });
  }

  q.addEventListener("input", render);
  q.addEventListener("focus", function () { carregar(); if (q.value.trim()) render(); });
  q.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") { e.preventDefault(); if (res.hidden) render(); mover(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); mover(-1); }
    else if (e.key === "Escape") { fechar(); }
    else if (e.key === "Enter") {
      var ops = res.querySelectorAll("a[role=option]");
      var alvo = ops[sel >= 0 ? sel : 0];
      if (alvo && !res.hidden) { e.preventDefault(); location.href = alvo.href; }
    }
  });
  document.addEventListener("click", function (e) { if (!caixa.contains(e.target)) fechar(); });
})();
