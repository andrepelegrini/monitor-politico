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
