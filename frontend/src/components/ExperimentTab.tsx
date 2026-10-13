import { useState } from "react";
import type { SimText, SystemText } from "../domain/experiments";
import type { ModelKey } from "../domain/types";
import { SensitivityPanel } from "./SensitivityPanel";
import { ServersPanel } from "./ServersPanel";
import { SweepPanel } from "./SweepPanel";

type Mode = "sweep" | "servers" | "sensitivity";

const MODES: { key: Mode; label: string }[] = [
  { key: "sweep", label: "Varredura de parâmetro" },
  { key: "servers", label: "Comparar servidores" },
  { key: "sensitivity", label: "Sensibilidade" },
];

interface Props {
  /** Modelo e valores do Laboratório: os experimentos partem do mesmo sistema. */
  model: ModelKey;
  system: SystemText;
  sim: SimText;
}

/**
 * Fase 6: experimentos "e se...". Os três painéis ficam montados (só um visível), então
 * os resultados e os campos de cada um sobrevivem à troca de aba.
 */
export function ExperimentTab({ model, system, sim }: Props) {
  const [mode, setMode] = useState<Mode>("sweep");
  return (
    <div className="exp">
      <div className="panel exp-modes">
        <div role="tablist" aria-label="Tipo de experimento" className="tabs">
          {MODES.map((m) => (
            <button
              key={m.key}
              role="tab"
              type="button"
              id={`exp-tab-${m.key}`}
              aria-selected={mode === m.key}
              aria-controls={`exp-panel-${m.key}`}
              className="tab"
              onClick={() => setMode(m.key)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <SweepPanel active={mode === "sweep"} model={model} system={system} sim={sim} />
      <ServersPanel active={mode === "servers"} model={model} system={system} />
      <SensitivityPanel active={mode === "sensitivity"} model={model} system={system} />
    </div>
  );
}
