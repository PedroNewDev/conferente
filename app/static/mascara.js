function mascaraCnpj(valor) {
  const digitos = valor.replace(/\D/g, "").slice(0, 14);
  let saida = digitos;
  if (digitos.length > 12) {
    saida = digitos.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{0,2})$/, "$1.$2.$3/$4-$5");
  } else if (digitos.length > 8) {
    saida = digitos.replace(/^(\d{2})(\d{3})(\d{3})(\d{0,4})$/, "$1.$2.$3/$4");
  } else if (digitos.length > 5) {
    saida = digitos.replace(/^(\d{2})(\d{3})(\d{0,3})$/, "$1.$2.$3");
  } else if (digitos.length > 2) {
    saida = digitos.replace(/^(\d{2})(\d{0,3})$/, "$1.$2");
  }
  return saida;
}

document.querySelectorAll('input[name="cnpj"]').forEach((campo) => {
  campo.setAttribute("maxlength", "18");
  campo.setAttribute("inputmode", "numeric");
  campo.addEventListener("input", () => {
    campo.value = mascaraCnpj(campo.value);
  });
});
