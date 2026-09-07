const ICONOS_SVG = {
  laptop:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M2 18h20l-1.4 2.3a1 1 0 0 1-.86.7H4.26a1 1 0 0 1-.86-.7L2 18z"/></svg>',
  monitor:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/></svg>',
  camisa:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3 4 7l3 3v11h10V10l3-3-4-4-2 2h-4L8 3Z"/></svg>',
  generico:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="1.5"/><path d="m21 15-5-5L4 21"/></svg>',
};

const VISUAL_CATEGORIA = {
  2: { icono: "laptop", fondo: "bg-[#eeece7]" },
  3: { icono: "monitor", fondo: "bg-[#e8ebee]" },
  5: { icono: "camisa", fondo: "bg-[#f2e9e3]" },
};

export function categoriaVisual(idCategoria) {
  const v = VISUAL_CATEGORIA[idCategoria] || { icono: "generico", fondo: "bg-neutral-100" };
  return { ...v, svg: ICONOS_SVG[v.icono] };
}
