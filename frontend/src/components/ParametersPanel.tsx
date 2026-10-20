import { IconClock, IconPlayerPlay, IconPlayerStop } from "@tabler/icons-react";
import { LAB_MODEL_ORDER, MODELS, usesService } from "../domain/models";
import { ErlangSizing } from "./ErlangSizing";
import { DISTRIBUTIONS, distributionInfo, serviceSummary } from "../domain/service";
import type { Action, FieldErrors, FieldKey, FormValues, ModelKey } from "../domain/types";

interface FieldProps {
  field: FieldKey;
  label: string;
  value: string;
  error?: string;
  hint?: string;
  onChange: (field: FieldKey, value: string) => void;
}

function Field({ field, label, value, error, hint, onChange }: FieldProps) {
  const id = `field-${field}`;
  return (
    <div className={error ? "field has-error" : "field"}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        value={value}
        inputMode="decimal"
        autoComplete="off"
        aria-invalid={error ? true : undefined}
        aria-describedby={error || hint ? `${id}-note` : undefined}
        onChange={(e) => onChange(field, e.target.value)}
      />
      {error ? (
        <span id={`${id}-note`} className="field-error" role="alert">{error}</span>
      ) : hint ? (
        <span id={`${id}-note`} className="field-hint">{hint}</span>
      ) : null}
    </div>
  );
}

function ServiceFields({ model, values, errors, onChange }: {
  model: ModelKey; values: FormValues; errors: FieldErrors; onChange: (field: FieldKey, value: string) => void;
}) {
  const info = distributionInfo(values.distribution);
  const summary = serviceSummary(values);
  return (
    <>
      <div className={errors.distribution ? "field has-error" : "field"}>
        <label htmlFor="field-distribution">Distribuição do serviço</label>
        <select
          id="field-distribution"
          value={info.key}
          onChange={(e) => onChange("distribution", e.target.value)}
        >
          {DISTRIBUTIONS.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
        </select>
      </div>
      <div className="grid2">
        {info.fields.map((f) => (
          <Field
            key={`${info.key}-${f.field}`} field={f.field} label={f.label} value={values[f.field]}
            error={errors[f.field]} hint={f.hint} onChange={onChange}
          />
        ))}
      </div>
      {summary && <p className="service-summary" aria-label="Resumo do serviço">{summary}</p>}
      {model === "mgc" ? (
        <p className="field-hint" role="note">
          Com vários servidores não há fórmula exata: o cálculo usa a aproximação de Allen–Cunneen, que escala
          a fila do M/M/c por (1 + CV²)/2. É exata com c = 1 ou serviço exponencial; a simulação mostra o erro nos demais casos.
        </p>
      ) : info.key !== "exponential" && (
        <p className="field-hint" role="note">
          Serviço não exponencial: o modelo deixa de ser markoviano. As médias seguem a fórmula de
          Pollaczek-Khinchine, que usa só a média e a variância do serviço.
        </p>
      )}
    </>
  );
}

interface Props {
  model: ModelKey;
  values: FormValues;
  errors: FieldErrors;
  estimate: string | null;
  busy: boolean;
  onModelChange: (model: ModelKey) => void;
  onChange: (field: FieldKey, value: string) => void;
  onRun: (action: Action) => void;
  onCancel: () => void;
}

export function ParametersPanel({
  model, values, errors, estimate, busy, onModelChange, onChange, onRun, onCancel,
}: Props) {
  const info = MODELS[model];
  const common = { onChange };
  const multi = info.usesServers;

  return (
    <form
      className="panel params"
      aria-label="Parâmetros do modelo"
      onSubmit={(e) => {
        e.preventDefault();
        onRun("compare");
      }}
    >
      <div className="field model-select">
        <label htmlFor="field-model">Modelo</label>
        <select
          id="field-model"
          value={model}
          onChange={(e) => onModelChange(e.target.value as ModelKey)}
        >
          {LAB_MODEL_ORDER.map((key) => (
            <option key={key} value={key}>{MODELS[key].label}</option>
          ))}
        </select>
      </div>

      <h2 className="group-title">Sistema</h2>
      {usesService(model) ? (
        <div className="stack">
          <div className="grid2">
            <Field {...common} field="lambda" label="Chegadas λ (req/s)" value={values.lambda} error={errors.lambda} />
            {info.usesServers && (
              <Field {...common} field="servers" label="Servidores c" value={values.servers} error={errors.servers} />
            )}
          </div>
          <ServiceFields model={model} values={values} errors={errors} onChange={onChange} />
        </div>
      ) : (
        <div className="grid2">
          <Field {...common} field="lambda" label="Chegadas λ (req/s)" value={values.lambda} error={errors.lambda} />
          <Field
            {...common} field="mu" value={values.mu} error={errors.mu}
            label={multi ? "Serviço μ (por servidor)" : "Serviço μ (req/s)"}
          />
          {info.usesServers && (
            <Field {...common} field="servers" label="Servidores c" value={values.servers} error={errors.servers} />
          )}
          {info.usesCapacity && (
            <Field
              {...common} field="capacity" label="Capacidade K" value={values.capacity}
              error={errors.capacity} hint="Fila + em atendimento"
            />
          )}
        </div>
      )}

      {model === "erlangb" && (
        <ErlangSizing
          lambda={values.lambda} mu={values.mu}
          onApply={(servers) => onChange("servers", String(servers))}
        />
      )}
      {model === "erlangb" && (
        <p className="field-hint" role="note">
          Sistema de perda: sem fila, quem chega com todos os servidores ocupados é recusado.
          Tráfego oferecido a = λ/μ, em Erlangs.
        </p>
      )}

      <h2 className="group-title">Simulação</h2>
      <div className="grid2">
        <Field {...common} field="simulationTime" label="Tempo (s)" value={values.simulationTime} error={errors.simulationTime} />
        <Field {...common} field="replications" label="Réplicas" value={values.replications} error={errors.replications} hint="De 2 a 100" />
        <Field {...common} field="warmupTime" label="Warm-up (s)" value={values.warmupTime} error={errors.warmupTime} />
        <Field {...common} field="seed" label="Semente" value={values.seed} error={errors.seed} hint="Vazio = aleatória" />
      </div>

      {estimate && (
        <p className="estimate">
          <IconClock size={16} aria-hidden="true" />
          {estimate}
        </p>
      )}

      {busy ? (
        <button type="button" className="btn btn-block" onClick={onCancel}>
          <IconPlayerStop size={16} aria-hidden="true" /> Cancelar
        </button>
      ) : (
        <div className="actions">
          <button type="submit" className="btn btn-primary btn-block">
            <IconPlayerPlay size={16} aria-hidden="true" /> Comparar
          </button>
          <div className="grid2">
            <button type="button" className="btn" onClick={() => onRun("calculate")}>Só calcular</button>
            <button type="button" className="btn" onClick={() => onRun("simulate")}>Só simular</button>
          </div>
        </div>
      )}
    </form>
  );
}
