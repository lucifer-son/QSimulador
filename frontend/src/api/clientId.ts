/**
 * Identificador anônimo deste navegador, enviado ao histórico (cabeçalho X-Client-Id).
 * Organiza os registros por navegador; não é autenticação.
 */
const STORAGE_KEY = "qsimulador-client-id";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

let memoryId: string | null = null;

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // Fallback para navegadores sem crypto.randomUUID (contexto não seguro).
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function getClientId(): string {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved && UUID.test(saved)) return saved;
    const created = newId();
    window.localStorage.setItem(STORAGE_KEY, created);
    return created;
  } catch {
    // Armazenamento bloqueado: vale só até recarregar a página.
    memoryId ??= newId();
    return memoryId;
  }
}
