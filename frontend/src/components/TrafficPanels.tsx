import { IconPlus, IconTrash } from "@tabler/icons-react";
import { blankPlan, MAX_PLANS, type PlanText, type SweepText, type TrafficErrors } from "../domain/traffic";
import { TextField } from "./TextField";

/** Os planos alternativos: o que trocar em cada fase (vazio = mantém o da referência). */
export function PlansPanel({
  plans, errors, bonferroni, onChange, onBonferroni, nextId,
}: {
  plans: PlanText[]; errors: TrafficErrors; bonferroni: boolean;
  onChange: (plans: PlanText[]) => void; onBonferroni: (v: boolean) => void; nextId: () => number;
}) {
  const update = (id: number, patch: Partial<PlanText>) => onChange(plans.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  return (
    <fieldset className="scenario-card">
      <legend>Planos alternativos</legend>
      <p className="sub">Cada plano troca só o que você preencher; o resto fica como no formulário (a referência). Para isolar o efeito da redistribuição do verde, mantenha o ciclo.</p>
      {plans.map((p, n) => (
        <div key={p.id} className="scenario-card" role="group" aria-label={`Plano ${n + 1}`}>
          <div className="field">
            <label htmlFor={`plan-${p.id}-name`}>Nome do plano {n + 1}</label>
            <input id={`plan-${p.id}-name`} value={p.name} placeholder={`Plano ${n + 1}`} onChange={(e) => update(p.id, { name: e.target.value })} />
          </div>
          <div className="grid2">
            <TextField id={`plan-${p.id}-g1`} label="Verde da fase 1 (s)" value={p.green1} error={errors[`plan.${p.id}.green1`]} onChange={(v) => update(p.id, { green1: v })} />
            <TextField id={`plan-${p.id}-g2`} label="Verde da fase 2 (s)" value={p.green2} error={errors[`plan.${p.id}.green2`]} onChange={(v) => update(p.id, { green2: v })} />
            <TextField id={`plan-${p.id}-y1`} label="Amarelo da fase 1 (s)" value={p.amber1} error={errors[`plan.${p.id}.amber1`]} onChange={(v) => update(p.id, { amber1: v })} />
            <TextField id={`plan-${p.id}-y2`} label="Amarelo da fase 2 (s)" value={p.amber2} error={errors[`plan.${p.id}.amber2`]} onChange={(v) => update(p.id, { amber2: v })} />
          </div>
          <button type="button" className="btn btn-small" onClick={() => onChange(plans.filter((x) => x.id !== p.id))}>
            <IconTrash size={14} aria-hidden="true" /> Remover plano {n + 1}
          </button>
        </div>
      ))}
      {errors.plans && <span className="field-error" role="alert">{errors.plans}</span>}
      <button type="button" className="btn btn-small" disabled={plans.length >= MAX_PLANS} onClick={() => onChange([...plans, blankPlan(nextId())])}>
        <IconPlus size={14} aria-hidden="true" /> Adicionar plano
      </button>
      <label className="check">
        <input type="checkbox" checked={bonferroni} onChange={(e) => onBonferroni(e.target.checked)} />
        Corrigir os ICs das diferenças pelo número de planos (Bonferroni)
      </label>
    </fieldset>
  );
}

export function SweepPanel({ value, errors, onChange }: { value: SweepText; errors: TrafficErrors; onChange: (v: SweepText) => void }) {
  return (
    <fieldset className="scenario-card">
      <legend>Varredura da divisão do verde</legend>
      <p className="sub">
        Mantém o ciclo e redistribui o verde total entre as fases, de verde mínimo a verde mínimo. O verde mínimo é uma restrição de segurança
        (por exemplo, travessia de pedestres) e quem conhece o cruzamento é quem define: não há valor padrão.
      </p>
      <div className="grid2">
        <TextField id="sweep-min1" label="Verde mínimo da fase 1 (s)" value={value.minGreen1} error={errors.minGreen1} onChange={(v) => onChange({ ...value, minGreen1: v })} />
        <TextField id="sweep-min2" label="Verde mínimo da fase 2 (s)" value={value.minGreen2} error={errors.minGreen2} onChange={(v) => onChange({ ...value, minGreen2: v })} />
      </div>
      <TextField id="sweep-step" label="Passo (s)" value={value.step} error={errors.step} hint="Até 40 pontos." onChange={(v) => onChange({ ...value, step: v })} />
    </fieldset>
  );
}
