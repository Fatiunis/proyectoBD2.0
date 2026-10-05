export const API_URL = "http://127.0.0.1:8000/api";

// Si el servidor no responde (caído, sin red, timeout), fetch lanza una
// excepción en vez de devolver una respuesta. Se convierte en una respuesta
// normal con status 0 y codigo SIN_CONEXION, para que cada pantalla pueda
// decirle al usuario qué pasó en vez de quedarse sin reaccionar.
export async function apiFetch(path, opts = {}) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
  } catch {
    return {
      ok: false,
      status: 0,
      data: { error: "No pudimos comunicarnos con el servidor. Revisa tu conexión e intenta de nuevo.", codigo: "SIN_CONEXION" },
    };
  }
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}
