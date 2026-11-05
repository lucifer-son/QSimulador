import { IconPlus, IconTrash } from "@tabler/icons-react";
import { blankPhase, blankPlan, MAX_PLANS, type PhaseText, type PlanText, type SweepText, type TrafficErrors } from "../domain/traffic";
import { TextField } from "./TextField";

/** Os planos alternativos: o que trocar em cada fase (vazio = mantém o da referência). */
export function PlansPanel({
  plans, errors, bonferroni, phaseCount, onChange, onBonferroni, nextId,
}: {
  plans: PlanText[]; errors: TrafficErrors; bonferroni: boolean; phaseCount: number;
  onChange: (plans: PlanText[]) => void; onBonferroni: (v: boolean) => void; nextId: () => number;
}) {
  const update = (id: number, patch: Partial<PlanText>) => onChange(plans.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  const setPhase = (plan: PlanText, i: number, patch: Partial<PhaseText>) =>
    update(plan.id, { phases: Array.from({ length: phaseCount }, (_, k) => (k === i ? { ...(plan.phases[k] ?? blankPhase()), ...patch } : plan.phases[k] ?? blankPhase())) });
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
            {Array.from({ length: phaseCount }, (_, i) => (
              <TextField key={`g${i}`} id={`plan-${p.id}-g${i + 1}`} label={`Verde da fase ${i + 1} (s)`} value={p.phases[i]?.green ?? ""}
                error={errors[`plan.${p.id}.green${i + 1}`]} onChange={(v) => setPhase(p, i, { green: v })} />
            ))}
            {Array.from({ length: phaseCount }, (_, i) => (
              <TextField key={`y${i}`} id={`plan-${p.id}-y${i + 1}`} label={`Amarelo da fase ${i + 1} (s)`} value={p.phases[i]?.amber ?? ""}
                error={errors[`plan.${p.id}.amber${i + 1}`]} onChange={(v) => setPhase(p, i, { amber: v })} />
            ))}
          </div>
          <button type="button" className="btn btn-small" onClick={() => onChange(plans.filter((x) => x.id !== p.id))}>
            <IconTrash size={14} aria-hidden="true" /> Remover plano {n + 1}
          </button>
        </div>
      ))}
      {errors.plans && <span className="field-error" role="alert">{errors.plans}</span>}
      <button type="button" className="btn btn-small" disabled={plans.length >= MAX_PLANS} onClick={() => onChange([...plans, blankPlan(nextId(), "", phaseCount)])}>
        <IconPlus size={14} aria-hidden="true" /> Adicionar plano
      </button>
      <label className="check">
        <input type="checkbox" checked={bonferroni} onChange={(e) => onBonferroni(e.target.checked)} />
        Corrigir os ICs das diferenças pelo número de planos (Bonferroni)
      </label>
    </fieldset>
  );
}

export function SweepPanel({ value, errors, phaseCount, onChange }: { value: SweepText; errors: TrafficErrors; phaseCount: number; onChange: (v: SweepText) => void }) {
  return (
    <fieldset className="scenario-card">
      <legend>Varredura da divisão do verde</legend>
      <p className="sub">
        Mantém o ciclo e redistribui o verde total de duas fases, de verde mínimo a verde mínimo; as demais fases não mudam.
        O verde mínimo é uma restrição de segurança (por exemplo, travessia de pedestres) e quem conhece o cruzamento é quem define: não há valor padrão.
      </p>
      {phaseCount > 2 && (
        <div className="grid2">
          <TextField id="sweep-pair1" label={`Primeira fase varrida (1 a ${phaseCount})`} value={value.pair1} error={errors.pair1} onChange={(v) => onChange({ ...value, pair1: v })} />
          <TextField id="sweep-pair2" label={`Segunda fase varrida (1 a ${phaseCount})`} value={value.pair2} error={errors.pair2} onChange={(v) => onChange({ ...value, pair2: v })} />
        </div>
      )}
      <div className="grid2">
        <TextField id="sweep-min1" label={`Verde mínimo da fase ${value.pair1 || 1} (s)`} value={value.minGreen1} error={errors.minGreen1} onChange={(v) => onChange({ ...value, minGreen1: v })} />
        <TextField id="sweep-min2" label={`Verde mínimo da fase ${value.pair2 || 2} (s)`} value={value.minGreen2} error={errors.minGreen2} onChange={(v) => onChange({ ...value, minGreen2: v })} />
      </div>
      <TextField id="sweep-step" label="Passo (s)" value={value.step} error={errors.step} hint="Até 40 pontos." onChange={(v) => onChange({ ...value, step: v })} />
    </fieldset>
  );
}
