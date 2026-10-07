export function formatoMinSeg(segundos) {
  const s = Math.max(0, Math.ceil(segundos));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function formatoCuentaRegresiva(segundos) {
  const s = Math.max(0, Math.ceil(segundos));
  const dias = Math.floor(s / 86400);
  const horas = Math.floor((s % 86400) / 3600);
  if (dias > 0) return `${dias}d ${horas}h`;
  const dos = (n) => String(n).padStart(2, "0");
  return `${dos(horas)}:${dos(Math.floor((s % 3600) / 60))}:${dos(s % 60)}`;
}
