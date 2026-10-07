import { IconClock, IconPlayerPlay, IconPlayerStop } from "@tabler/icons-react";
import { MODEL_ORDER, MODELS } from "../domain/models";
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
      <fieldset className="models">
        <legend>Modelo</legend>
        <div className="segmented">
          {MODEL_ORDER.map((key) => (
            <button
              key={key}
              type="button"
              className="seg"
              aria-pressed={key === model}
              onClick={() => onModelChange(key)}
            >
              {MODELS[key].label}
            </button>
          ))}
        </div>
      </fieldset>

      <h2 className="group-title">Sistema</h2>
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

      <h2 className="group-title">Simulação</h2>
      <div className="grid2">
        <Field {...common} field="simulationTime" label="Tempo (s)" value={values.simulationTime} error={errors.simulationTime} />
        <Field {...common} field="replications" label="Réplicas" value={values.replications} error={errors.replications} />
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
