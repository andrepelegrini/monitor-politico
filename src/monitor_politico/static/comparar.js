// Comparar parlamentares da mesma Casa. As pessoas escolhidas ficam no endereço (comparar.html#204534-204528),
// que pode ser compartilhado. Os votos de cada uma só são baixados quando ela entra na comparação.
(function () {
  var raiz = document.getElementById("cmp");
  if (!raiz) return;
  var MAX = Number(raiz.dataset.maximo) || 3;
  var senado = raiz.dataset.casa === "senado";
  var chips = document.getElementById("cmp-chips");
  var add = document.getElementById("cmp-add");
  var addCampo = document.getElementById("cmp-add-campo");
  var limite = document.getElementById("cmp-limite");
  var vazio = document.getElementById("cmp-vazio");
  var resultado = document.getElementById("cmp-resultado");
  var titulo = document.getElementById("cmp-titulo");
  var porId = {}, escolhidos = [], votos = {};

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function num(n) { return Number(n).toLocaleString("pt-BR"); }
  function brl(n) { return "R$ " + Math.round(n).toLocaleString("pt-BR"); }
  function pct(a, b) { return b ? Math.round(100 * a / b) : 0; }
  function nomes(lista) {
    var n = lista.map(function (p) { return p.nome; });
    return n.length < 2 ? n.join("") : n.slice(0, -1).join(", ") + " e " + n[n.length - 1];
  }

  function doEndereco() {
    var vistos = {};
    escolhidos = location.hash.slice(1).split("-").filter(function (id) {
      if (!porId[id] || vistos[id]) return false;
      vistos[id] = true;
      return true;
    }).slice(0, MAX);
  }
  function guardar() {
    history.replaceState(null, "", escolhidos.length ? "#" + escolhidos.join("-") : location.pathname);
  }

  // Uma linha de métrica: nome, barra na escala da linha e valor de cada pessoa.
  function linha(rotulo, sub, pessoas, valor, texto, escala) {
    var valores = pessoas.map(valor);
    var max = escala || Math.max.apply(null, valores.map(function (v) { return v == null ? 0 : v; }));
    return '<div class="cmp-metrica"><div class="cmp-rot">' + esc(rotulo) + (sub ? "<small>" + esc(sub) + "</small>" : "") + '</div><div class="cmp-valores">' +
      pessoas.map(function (p, i) {
        var v = valores[i];
        return '<div class="cmp-valor"><span class="cmp-quem">' + esc(p.nome) + '</span><span class="cmp-trilho" aria-hidden="true"><span style="width:' +
          (v == null || !max ? 0 : Math.round(100 * v / max)) + '%"></span></span><span class="cmp-num">' + (v == null ? '<small>Sem dado</small>' : texto(p, v)) + "</span></div>";
      }).join("") + "</div></div>";
  }

  function cabecas(pessoas) {
    return pessoas.map(function (p) {
      return '<div class="cmp-cabeca">' + (p.foto ? '<img src="' + esc(p.foto) + '" alt="" width="48" height="64" loading="lazy">' : '<span class="ce-photo-empty" aria-hidden="true"></span>') +
        '<span class="cmp-nome">' + esc(p.nome) + '</span><span class="ce-meta">' + esc(p.partido) + "-" + esc(p.uf) +
        (p.eleicao ? " · " + num(p.eleicao[1]) + " votos na eleição de " + p.eleicao[0] : "") + '</span><a href="' + p.id + '.html">Ver perfil completo</a></div>';
    }).join("");
  }

  function atuacao(pessoas) {
    function m(campo) { return function (p) { return p.m ? p.m[campo] : null; }; }
    var simples = function (p, v) { return num(v); };
    return [
      linha("Leis de autoria principal", "Projetos assinados em primeiro lugar que viraram lei", pessoas, m("principal"), simples),
      linha("Leis em coautoria", "", pessoas, m("coautoria"), simples),
      linha(senado ? "Votos nominais abertos" : "Votos registrados", senado ? "Votações nominais abertas do Plenário" : "Votações nominais do Plenário", pessoas, m("votos"), simples),
      linha(senado ? "Participação em votações" : "Presença",
        senado ? "Votações nominais em que votou ou presidiu, entre as que constava" : "Dias com presença, entre os dias com sessão em exercício", pessoas,
        function (p) { return p.m && p.m.dias ? pct(p.m.presencas, p.m.dias) : null; },
        function (p, v) { return num(p.m.presencas) + " <small>de " + num(p.m.dias) + (senado ? " votações" : " dias") + " · " + v + "%</small>"; }, 100),
      linha("Relatorias atuais", "Projetos com a pessoa como relatora no momento", pessoas, m("relatorias"), simples)
    ].join("");
  }

  function custo(pessoas) {
    var linhas = [
      linha("Cota parlamentar usada", senado ? "Despesas do mandato reembolsadas pelo Senado" : "Passagens, escritório, divulgação e outras despesas reembolsadas", pessoas,
        function (p) { return p.cota ? p.cota.total : null; },
        function (p, v) { return brl(v) + (p.cota.limite ? " <small>" + pct(v, p.cota.limite) + "% do limite</small>" : ""); })
    ];
    // Verba de gabinete: só depois da coleta que lê o quadro; até lá, a linha não aparece.
    if (!senado && pessoas.some(function (p) { return p.gabinete; })) {
      linhas.push(linha("Verba de gabinete usada", "Salários de até 25 secretários parlamentares", pessoas,
        function (p) { return p.gabinete ? p.gabinete.total : null; },
        function (p, v) { return brl(v) + " <small>" + pct(v, p.gabinete.disponivel) + "% do disponível</small>"; }));
    }
    return linhas.join("");
  }

  function maiores(pessoas) {
    return pessoas.filter(function (p) { return p.cota && p.cota.maior; }).map(function (p) {
      return '<p><span class="ce-meta">Maior gasto da cota de ' + esc(p.nome) + "</span><strong>" + esc(p.cota.maior[0]) + " · " + brl(p.cota.maior[1]) + "</strong></p>";
    }).join("");
  }

  function pares(pessoas) {
    var html = "";
    for (var i = 0; i < pessoas.length; i++) {
      for (var j = i + 1; j < pessoas.length; j++) {
        var a = votos[pessoas[i].id], b = votos[pessoas[j].id];
        var cabeca = '<div class="cmp-par"><span class="ce-meta">' + esc(pessoas[i].nome) + " e " + esc(pessoas[j].nome) + "</span>";
        if (!a || !b) { html += cabeca + '<span class="ce-meta">' + (a === null || b === null ? "Votos indisponíveis." : "Carregando…") + "</span></div>"; continue; }
        var r = concordancia(a, b);
        html += cabeca + (r[1]
          ? '<span class="cmp-pct">' + pct(r[0], r[1]) + "% <small>votos iguais</small></span>" +
            '<span class="cmp-trilho" aria-hidden="true"><span style="width:' + pct(r[0], r[1]) + '%"></span></span><span class="ce-meta">' + num(r[0]) + " de " + num(r[1]) + " votações</span>"
          : '<span class="ce-meta">Nenhuma votação em que as duas pessoas votaram Sim ou Não.</span>') + "</div>";
      }
    }
    return html;
  }

  function concordancia(a, b) {
    var lado = {};
    a.s.forEach(function (id) { lado[id] = "s"; });
    a.n.forEach(function (id) { lado[id] = "n"; });
    var iguais = 0, comuns = 0;
    b.s.forEach(function (id) { if (lado[id]) { comuns++; if (lado[id] === "s") iguais++; } });
    b.n.forEach(function (id) { if (lado[id]) { comuns++; if (lado[id] === "n") iguais++; } });
    return [iguais, comuns];
  }

  function carregarVotos(id) {
    if (id in votos) return;
    votos[id] = undefined;
    fetch(raiz.dataset.votos + id + ".json")
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { votos[id] = d; }, function () { votos[id] = null; })
      .then(function () { document.getElementById("cmp-pares").innerHTML = pares(escolhidos.map(function (x) { return porId[x]; })); });
  }

  function mostrar() {
    var pessoas = escolhidos.map(function (id) { return porId[id]; });
    chips.innerHTML = pessoas.map(function (p) {
      return '<li class="cmp-chip">' + esc(p.nome) + " · " + esc(p.partido) + "-" + esc(p.uf) +
        '<button type="button" data-tirar="' + p.id + '" aria-label="Tirar ' + esc(p.nome) + ' da comparação">×</button></li>';
    }).join("");
    Array.prototype.forEach.call(add.options, function (o) { if (o.value) o.disabled = escolhidos.indexOf(o.value) >= 0; });
    var cheio = escolhidos.length >= MAX;
    addCampo.hidden = cheio;
    limite.hidden = !cheio;
    var basta = pessoas.length >= 2;
    vazio.hidden = basta;
    resultado.hidden = !basta;
    titulo.textContent = basta ? nomes(pessoas) : titulo.dataset.padrao;
    if (!basta) return;
    document.getElementById("cmp-cabecas").innerHTML = cabecas(pessoas);
    document.getElementById("cmp-linhas-atuacao").innerHTML = atuacao(pessoas);
    document.getElementById("cmp-linhas-custo").innerHTML = custo(pessoas);
    document.getElementById("cmp-maiores").innerHTML = maiores(pessoas);
    escolhidos.forEach(carregarVotos);
    document.getElementById("cmp-pares").innerHTML = pares(pessoas);
  }

  chips.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-tirar]");
    if (!b) return;
    escolhidos = escolhidos.filter(function (id) { return id !== b.dataset.tirar; });
    guardar();
    mostrar();
    add.focus();
  });
  add.addEventListener("change", function () {
    if (add.value && escolhidos.length < MAX && escolhidos.indexOf(add.value) < 0) escolhidos.push(add.value);
    add.value = "";
    guardar();
    mostrar();
  });
  window.addEventListener("hashchange", function () { doEndereco(); mostrar(); });

  fetch(raiz.dataset.dados)
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (d) {
      d.pessoas.forEach(function (p) {
        p.id = String(p.id);
        porId[p.id] = p;
        var o = document.createElement("option");
        o.value = p.id;
        o.textContent = p.nome + " · " + p.partido + "-" + p.uf;
        add.appendChild(o);
      });
      raiz.hidden = false;
      doEndereco();
      mostrar();
    })
    .catch(function () {
      vazio.textContent = "Não foi possível carregar os dados. Recarregue a página e tente de novo.";
      raiz.hidden = false;
      resultado.hidden = true;
    });
})();
