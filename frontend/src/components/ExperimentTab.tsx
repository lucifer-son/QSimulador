import { useState } from "react";
import type { SimText, SystemText } from "../domain/experiments";
import type { ExperimentModelKey } from "../domain/types";
import { SensitivityPanel } from "./SensitivityPanel";
import { ServersPanel } from "./ServersPanel";
import { ServicesPanel } from "./ServicesPanel";
import { SweepPanel } from "./SweepPanel";

type Mode = "sweep" | "servers" | "services" | "sensitivity";

const SWEEP: { key: Mode; label: string } = { key: "sweep", label: "Varredura de parâmetro" };
const SENSITIVITY: { key: Mode; label: string } = { key: "sensitivity", label: "Sensibilidade" };
/** O M/G/1 tem um servidor só: em vez de comparar servidores, compara distribuições de serviço. */
const modesFor = (model: ExperimentModelKey) => [
  SWEEP,
  model === "mg1"
    ? { key: "services" as Mode, label: "Comparar distribuições" }
    : { key: "servers" as Mode, label: "Comparar servidores" },
  SENSITIVITY,
];

interface Props {
  /** Modelo e valores do Laboratório: os experimentos partem do mesmo sistema. */
  model: ExperimentModelKey;
  system: SystemText;
  sim: SimText;
}

/**
 * Fase 6: experimentos "e se...". Os três painéis (varredura, comparação e sensibilidade) ficam montados (só um visível), então
 * os resultados e os campos de cada um sobrevivem à troca de aba.
 */
export function ExperimentTab({ model, system, sim }: Props) {
  const [chosen, setMode] = useState<Mode>("sweep");
  const modes = modesFor(model);
  const mode = modes.some((m) => m.key === chosen) ? chosen : "sweep";   // trocar de modelo pode tirar uma aba
  return (
    <div className="exp">
      <div className="panel exp-modes">
        <div role="tablist" aria-label="Tipo de experimento" className="tabs">
          {modes.map((m) => (
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
      {model === "mg1"
        ? <ServicesPanel active={mode === "services"} model={model} system={system} />
        : <ServersPanel active={mode === "servers"} model={model} system={system} />}
      <SensitivityPanel active={mode === "sensitivity"} model={model} system={system} />
    </div>
  );
}
