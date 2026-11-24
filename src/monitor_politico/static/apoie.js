// Copiar a chave Pix. Se o navegador não deixar, seleciona o texto para a pessoa copiar.
(function () {
  var botao = document.getElementById("ap-copiar");
  if (!botao) return;
  var chave = document.getElementById("ap-chave"), aviso = document.getElementById("ap-aviso");
  botao.hidden = false;
  function selecionar() {
    var faixa = document.createRange(), selecao = window.getSelection();
    faixa.selectNodeContents(chave);
    selecao.removeAllRanges();
    selecao.addRange(faixa);
    aviso.textContent = "Chave selecionada. Copie pelo teclado ou pelo menu.";
  }
  botao.addEventListener("click", function () {
    if (!navigator.clipboard) { selecionar(); return; }
    navigator.clipboard.writeText(chave.textContent).then(function () { aviso.textContent = "Chave copiada."; }, selecionar);
  });
})();
