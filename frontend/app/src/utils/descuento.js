// Mismo redondeo que el servidor (ROUND_HALF_UP): se calcula en centavos enteros porque con floats
// (1 - 1749/2200) * 100 da 20.4999… y Math.round lo deja en 20 en vez de 21.
function pctHalfUp(oferta, base) {
  const baseCent = Math.round(base * 100);
  const num = (baseCent - Math.round(oferta * 100)) * 100;
  return Math.floor((2 * num + baseCent) / (2 * baseCent));
}

// Redondear puede dar 100 % aunque el precio de oferta no sea 0 (p. ej. 4359 -> 1 = 99.98 %),
// así que mientras se cobre algo se muestra como máximo 99 %.
export function porcentajeDescuento(precioOferta, precioBase, pctServidor = null) {
  const oferta = Number(precioOferta);
  const base = Number(precioBase);
  let pct = pctServidor != null ? Math.round(pctServidor) : base > 0 ? pctHalfUp(oferta, base) : 0;
  if (oferta > 0) pct = Math.min(pct, 99);
  return Math.max(pct, 0);
}
