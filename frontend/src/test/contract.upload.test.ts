// @vitest-environment node
/**
 * Teste de contrato do upload (multipart) contra a API real. Roda no ambiente `node`, porque o FormData e o
 * File do jsdom não são os que o fetch do Node sabe enviar. Só executa com VITE_API_BASE_URL apontando para a API:
 *
 *   bash:        VITE_API_BASE_URL=http://127.0.0.1:8000 npm run test:contract
 */
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { importLevels } from "../api/realdataExtra";
import { fixtures } from "./helpers";

const live = Boolean(import.meta.env.VITE_API_BASE_URL);
const keys = (o: unknown) => Object.keys(o as object).sort();

const CSV = "users,avg_ms,p90_ms,throughput,error_rate\n1,196,460,0.81,0\n5,385,916,3.55,0\n10,1072,2386,5.0,0\n";
const form = (name = "niveis.csv") => {
  const f = new FormData();
  f.append("file", new File([CSV], name, { type: "text/csv" }));
  return f;
};

describe.skipIf(!live)("contrato do upload de níveis de carga com a API real", () => {
  it("importação: formato igual ao da fixture", async () => {
    const r = await importLevels(form());
    expect(keys(r)).toEqual(keys(fixtures.realdataLevelsImport));
    expect(keys(r.suggestions)).toEqual(keys(fixtures.realdataLevelsImport.suggestions));
    expect(keys(r.levels[0])).toEqual(keys(fixtures.realdataLevelsImport.levels[0]));
    expect(keys(r.levels[0].metrics)).toEqual(keys(fixtures.realdataLevelsImport.levels[0].metrics));
    expect(r.levels.map((l) => l.users)).toEqual([1, 5, 10]);
    expect(r.suggestions.base_users).toBe(1);
  });

  it("arquivo inválido chega como invalid_dataset, com o campo", async () => {
    const bad = await importLevels(form("niveis.txt")).catch((e: unknown) => e);
    expect(bad).toBeInstanceOf(ApiError);
    expect((bad as ApiError).code).toBe("invalid_dataset");
    expect((bad as ApiError).fields?.[0].field).toBe("file");
  });
});
