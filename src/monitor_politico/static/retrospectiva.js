// Imagens da retrospectiva (feed e stories), desenhadas no navegador com os números da página.
// Nada é guardado no servidor: as imagens saem sempre com os dados da última coleta.
(function () {
  var area = document.getElementById("rt-imagens-area");
  if (!area || !window.HTMLCanvasElement) return;

  var CORES = { papel: "#FAF8F4", tinta: "#26221E", sec: "#5C544B", fraco: "#6E6459", borda: "#E7E1D8", marinho: "#14263D", destaque: "#A4482B" };
  var SERIFA = "Fraunces, Georgia, serif";
  var SANS = "'Instrument Sans', system-ui, sans-serif";
  var FORMATOS = { feed: { largura: 1080, altura: 1350, colunas: 2 }, story: { largura: 1080, altura: 1920, colunas: 1 } };

  var dados = area.dataset;
  var numeros = JSON.parse(dados.numeros);
  var site = location.host;

  function quebrar(ctx, texto, largura) {
    var linhas = [], atual = "";
    texto.split(" ").forEach(function (palavra) {
      var teste = atual ? atual + " " + palavra : palavra;
      if (ctx.measureText(teste).width > largura && atual) { linhas.push(atual); atual = palavra; } else { atual = teste; }
    });
    if (atual) linhas.push(atual);
    return linhas;
  }

  function ajustar(ctx, texto, peso, tamanho, familia, largura) {
    var t = tamanho;
    do { ctx.font = peso + " " + t + "px " + familia; t -= 4; } while (ctx.measureText(texto).width > largura && t > 40);
  }

  function desenhar(formato, logo) {
    var f = FORMATOS[formato];
    var tela = document.createElement("canvas");
    tela.width = f.largura; tela.height = f.altura;
    var ctx = tela.getContext("2d");
    var margem = 72, util = f.largura - margem * 2;

    ctx.fillStyle = CORES.papel; ctx.fillRect(0, 0, f.largura, f.altura);
    ctx.fillStyle = CORES.marinho; ctx.fillRect(0, 0, f.largura, 150);
    if (logo) ctx.drawImage(logo, margem, 35, 80, 80);
    ctx.fillStyle = "#FFFFFF"; ctx.font = "600 40px " + SERIFA; ctx.textBaseline = "middle";
    ctx.fillText("MONITOR POLÍTICO", margem + 104, 77);

    ctx.textBaseline = "alphabetic";
    var y = formato === "story" ? 300 : 260;
    ctx.fillStyle = CORES.destaque; ctx.font = "700 30px " + SANS;
    ctx.fillText("RETROSPECTIVA DA LEGISLATURA 2023–2027", margem, y);
    y += 100;
    ctx.fillStyle = CORES.tinta; ajustar(ctx, dados.nome, "500", formato === "story" ? 104 : 96, SERIFA, util);
    ctx.fillText(dados.nome, margem, y);
    y += 62;
    ctx.fillStyle = CORES.sec; ctx.font = "400 36px " + SANS; ctx.fillText(dados.sub, margem, y);
    y += formato === "story" ? 90 : 70;
    ctx.fillStyle = CORES.borda; ctx.fillRect(margem, y, util, 2);
    y += formato === "story" ? 90 : 70;

    var largura = (util - (f.colunas - 1) * 48) / f.colunas;
    var altura = formato === "story" ? 250 : 330;
    numeros.forEach(function (n, i) {
      var col = i % f.colunas, lin = Math.floor(i / f.colunas);
      var x = margem + col * (largura + 48), topo = y + lin * altura;
      ctx.fillStyle = CORES.tinta; ctx.font = "500 " + (formato === "story" ? 104 : 112) + "px " + SERIFA;
      ctx.fillText(n.valor, x, topo + 96);
      ctx.fillStyle = CORES.sec; ctx.font = "400 34px " + SANS;
      quebrar(ctx, formato === "story" ? n.detalhe : n.rotulo, largura).slice(0, 3).forEach(function (linha, k) {
        ctx.fillText(linha, x, topo + 150 + k * 44);
      });
    });

    ctx.fillStyle = CORES.borda; ctx.fillRect(margem, f.altura - 130, util, 2);
    ctx.fillStyle = CORES.fraco; ctx.font = "400 28px " + SANS;
    ctx.fillText("Dados oficiais até " + dados.coleta + " · " + site, margem, f.altura - 70);
    return tela;
  }

  function carregarLogo() {
    return new Promise(function (ok) {
      var img = new Image();
      img.onload = function () { ok(img); };
      img.onerror = function () { ok(null); };
      img.src = dados.logo;
    });
  }

  var fontes = document.fonts && document.fonts.load
    ? Promise.all([document.fonts.load("500 96px Fraunces"), document.fonts.load("600 40px Fraunces"), document.fonts.load("400 34px 'Instrument Sans'"), document.fonts.load("700 30px 'Instrument Sans'")]).catch(function () {})
    : Promise.resolve();

  Promise.all([fontes, carregarLogo()]).then(function (r) {
    var logo = r[1];
    var telas = { feed: desenhar("feed", logo), story: desenhar("story", logo) };
    document.getElementById("rt-prev-feed").src = telas.feed.toDataURL("image/jpeg", 0.85);
    document.getElementById("rt-prev-story").src = telas.story.toDataURL("image/jpeg", 0.85);
    Array.prototype.forEach.call(area.querySelectorAll("[data-formato]"), function (botao) {
      botao.addEventListener("click", function () {
        telas[botao.dataset.formato].toBlob(function (blob) {
          var nome = dados.arquivo + "-" + botao.dataset.formato + ".jpg";
          var arquivo = window.File ? new File([blob], nome, { type: "image/jpeg" }) : null;
          // No celular, abre o compartilhamento do sistema com a imagem; no computador, baixa o arquivo.
          if (arquivo && navigator.canShare && navigator.canShare({ files: [arquivo] })) {
            navigator.share({ files: [arquivo], text: document.title, url: location.origin + location.pathname }).catch(function () {});
            return;
          }
          var link = document.createElement("a");
          link.href = URL.createObjectURL(blob);
          link.download = nome;
          document.body.appendChild(link);
          link.click();
          setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 1000);
        }, "image/jpeg", 0.9);
      });
    });
    area.hidden = false;
  });
})();
