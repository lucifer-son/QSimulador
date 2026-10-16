import { vi } from "vitest";
import experimentSensitivityMm1 from "./fixtures/experiment-sensitivity-mm1.json";
import experimentServersMmc from "./fixtures/experiment-servers-mmc.json";
import experimentSweepMm1 from "./fixtures/experiment-sweep-mm1.json";
import errorInvalidParameter from "./fixtures/error-invalid-parameter.json";
import errorInvalidRequest from "./fixtures/error-invalid-request.json";
import errorReplications from "./fixtures/error-replications.json";
import errorUnstable from "./fixtures/error-unstable.json";
import errorInvalidDataset from "./fixtures/error-invalid-dataset.json";
import realdataAnalyzeClosed from "./fixtures/realdata-analyze-closed.json";
import realdataCompareMmcn from "./fixtures/realdata-compare-mmcn.json";
import realdataCompareSimulated from "./fixtures/realdata-compare-simulated.json";
import realdataLevelsError from "./fixtures/realdata-levels-error.json";
import realdataLevelsImport from "./fixtures/realdata-levels-import.json";
import realdataReport from "./fixtures/realdata-report.json";
import mm1Calculate from "./fixtures/mm1-calculate.json";
import mm1Compare from "./fixtures/mm1-compare.json";
import mm1Simulate from "./fixtures/mm1-simulate.json";
import mmcCalculate from "./fixtures/mmc-calculate.json";
import mmcCompare from "./fixtures/mmc-compare.json";
import mmcSimulate from "./fixtures/mmc-simulate.json";
import mmckCalculate from "./fixtures/mmck-calculate.json";
import mmckCompare from "./fixtures/mmck-compare.json";
import mmckSimulate from "./fixtures/mmck-simulate.json";
import type { ThemeColors } from "../hooks/useThemeColors";

/** Respostas reais da API, gravadas em arquivos (ver src/test/fixtures). */
export const fixtures = {
  errorInvalidParameter, errorInvalidRequest, errorReplications, errorUnstable, errorInvalidDataset,
  realdataAnalyzeClosed, realdataCompareMmcn,
  realdataCompareSimulated, realdataLevelsError, realdataLevelsImport, realdataReport,
  experimentSensitivityMm1, experimentServersMmc, experimentSweepMm1,
  mm1Calculate, mm1Compare, mm1Simulate,
  mmcCalculate, mmcCompare, mmcSimulate,
  mmckCalculate, mmckCompare, mmckSimulate,
};

export const colors: ThemeColors = {
  text: "#111111", textSecondary: "#222222", textMuted: "#333333",
  border: "#444444", accent: "#0000ff", danger: "#ff0000",
};

/** Cópia profunda, para um teste poder alterar a fixture sem afetar os outros. */
export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export interface FakeReply { status?: number; body: unknown }
export type FakeHandler = (url: string, body: Record<string, unknown>) => FakeReply | Promise<FakeReply>;

// ---------- Histórico (/api/records) ----------

interface StoredRecord {
  id: string; kind: string; title: string; app_version: string | null; size_bytes: number;
  created_at: string; updated_at: string; params: Record<string, unknown>; result: Record<string, unknown>;
}
export interface RecordsCall { method: string; url: string; clientId: string | null; body: Record<string, unknown> }

const jsonResponse = (status: number, body: unknown) =>
  new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** API de histórico em memória, no mesmo contrato do backend. Fica fora da contagem do mockFetch. */
export class FakeRecords {
  readonly store: StoredRecord[] = [];
  readonly calls: RecordsCall[] = [];
  private seq = 0;
  /** Faz o próximo pedido (que não seja o /status) falhar com este erro. */
  failNext: { status: number; code: string; message: string } | null = null;

  constructor(public enabled = false, public limits = { max_record_bytes: 2_000_000, max_records_per_client: 200 }) {}

  add(partial: Partial<StoredRecord> & Pick<StoredRecord, "kind" | "title" | "params" | "result">): StoredRecord {
    this.seq += 1;
    const stamp = new Date(Date.UTC(2026, 9, 15, 12, this.seq)).toISOString();
    const record: StoredRecord = {
      id: `00000000-0000-4000-8000-${String(this.seq).padStart(12, "0")}`, app_version: null,
      size_bytes: JSON.stringify(partial.result).length, created_at: stamp, updated_at: stamp, ...partial,
    };
    this.store.push(record);
    return record;
  }

  handle(url: string, init?: RequestInit): Response {
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = new Headers(init?.headers as HeadersInit | undefined);
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {};
    this.calls.push({ method, url, clientId: headers.get("X-Client-Id"), body });
    const parsed = new URL(url, "http://x");
    const path = parsed.pathname.replace(/\/$/, "");

    if (path === "/api/records/status") {
      return jsonResponse(200, { enabled: this.enabled, ...this.limits });
    }
    if (!this.enabled) {
      return jsonResponse(503, { code: "persistence_disabled", message: "A persistência não está configurada neste servidor." });
    }
    if (this.failNext) {
      const { status, code, message } = this.failNext;
      this.failNext = null;
      return jsonResponse(status, { code, message });
    }
    const client = headers.get("X-Client-Id");
    if (!client || !UUID.test(client)) {
      return jsonResponse(422, { code: "invalid_client_id", message: "O cabeçalho X-Client-Id é obrigatório." });
    }
    const id = path.split("/")[3];
    const found = id ? this.store.find((r) => r.id === id) : undefined;
    const notFound = () => jsonResponse(404, { code: "record_not_found", message: "Registro não encontrado." });

    if (path === "/api/records" && method === "POST") {
      const record = this.add({
        kind: String(body.kind), title: String(body.title),
        params: body.params as Record<string, unknown>, result: body.result as Record<string, unknown>,
      });
      return jsonResponse(201, record);
    }
    if (path === "/api/records" && method === "GET") {
      const kind = parsed.searchParams.get("kind");
      const limit = Number(parsed.searchParams.get("limit") ?? 20);
      const offset = Number(parsed.searchParams.get("offset") ?? 0);
      const all = this.store.filter((r) => !kind || r.kind === kind).slice().reverse();
      const items = all.slice(offset, offset + limit).map(({ params: _p, result: _r, ...summary }) => summary);
      return jsonResponse(200, { items, total: all.length, limit, offset });
    }
    if (!found) return notFound();
    if (method === "GET") return jsonResponse(200, found);
    if (method === "PATCH") {
      found.title = String(body.title);
      const { params: _p, result: _r, ...summary } = found;
      return jsonResponse(200, summary);
    }
    this.store.splice(this.store.indexOf(found), 1);
    return jsonResponse(204, null);
  }
}

/** Manda /api/records para o FakeRecords e o resto para `fn`; assim `fn` só conta chamadas de cálculo. */
function route(fn: (url: string, init?: RequestInit) => Promise<Response>, records: FakeRecords) {
  return (url: string, init?: RequestInit) =>
    String(url).startsWith("/api/records") ? Promise.resolve(records.handle(String(url), init)) : fn(url, init);
}

/** Substitui o fetch global; devolve o mock para inspecionar as chamadas. */
export function mockFetch(handler: FakeHandler, records: FakeRecords = new FakeRecords(false)) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    // Envios de arquivo (FormData) não são JSON: o corpo chega vazio ao handler.
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : {};
    const reply = await handler(url, body);
    return new Response(JSON.stringify(reply.body), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", route(fn, records));
  return fn;
}

/** fetch que nunca responde, só rejeita quando a requisição é cancelada. */
export function mockPendingFetch(records: FakeRecords = new FakeRecords(false)) {
  const fn = vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      }),
  );
  vi.stubGlobal("fetch", route(fn, records));
  return fn;
}
