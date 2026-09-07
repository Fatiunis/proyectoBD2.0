import { ref } from "vue";

const CLAVE_SESION = "usuario_tiendaya";

function leerSesionInicial() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_SESION));
  } catch {
    return null;
  }
}

const sesion = ref(leerSesionInicial());

function setSesion(usuario) {
  localStorage.setItem(CLAVE_SESION, JSON.stringify(usuario));
  sesion.value = usuario;
}

function limpiarSesion() {
  localStorage.removeItem(CLAVE_SESION);
  sesion.value = null;
}

export function useSesion() {
  return { sesion, setSesion, limpiarSesion };
}
