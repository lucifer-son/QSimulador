// @vitest-environment node
/**
 * Contrato do upload das planilhas do vídeo (Fase 13.1) contra a API real. Roda no ambiente `node`, porque o
 * FormData e o File do jsdom não são os que o fetch do Node sabe enviar. Só executa com VITE_API_BASE_URL.
 */
import { describe, expect, it } from "vitest";
import { estimateVideo, validateVideo } from "../api/traffic";

const live = Boolean(import.meta.env.VITE_API_BASE_URL);
const csv = (text: string, name: string) => new File([text], name, { type: "text/csv" });

describe.skipIf(!live)("contrato do upload do vídeo com a API real", () => {
  it("estima e valida com planilhas pequenas", async () => {
    const signal = ["timestamp,approach_id,signal_state"];
    for (const [a, shift] of [["A", 0], ["B", 35]] as const) {
      for (let k = -1; k < 9; k++) {
        const t = shift + 70 * k;
        signal.push(`${t},${a},verde`, `${t + 30},${a},amarelo`, `${t + 33},${a},vermelho`);
      }
    }
    const counts = ["interval_start,interval_end,approach_id,arrivals,departures,queue_count"];
    for (const a of ["A", "B"]) for (let j = 0; j < 9; j++) counts.push(`${j * 60},${(j + 1) * 60},${a},10,9,${j % 3}`);
    const form = new FormData();
    form.append("signal_events", csv(signal.join("\n"), "s.csv"));
    form.append("counts", csv(counts.join("\n"), "c.csv"));
    const estimate = await estimateVideo(form);
    expect(estimate.signal.phases[0].green).toBeCloseTo(30);
    expect(estimate.discharge).toBeNull();
    expect(estimate.suggested.approaches[0].headway).toBeNull();

    const bad = new FormData();
    bad.append("signal_events", csv("a,b\n1,2\n", "s.csv"));
    bad.append("counts", csv(counts.join("\n"), "c.csv"));
    await expect(estimateVideo(bad)).rejects.toMatchObject({ code: "invalid_dataset" });
    const invalid = new FormData();
    invalid.append("signal_events", csv(signal.join("\n"), "s.csv"));
    invalid.append("counts", csv(counts.join("\n"), "c.csv"));
    invalid.append("config", "{nope");
    await expect(validateVideo(invalid)).rejects.toMatchObject({ code: "invalid_parameter", fields: [{ field: "config" }] });
  });
});
