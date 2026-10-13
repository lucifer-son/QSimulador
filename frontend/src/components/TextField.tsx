interface Props {
  id: string;
  label: string;
  value: string;
  error?: string;
  hint?: string;
  onChange: (value: string) => void;
}

/** Campo de texto numérico com rótulo, dica e erro (o mesmo visual do formulário do Laboratório). */
export function TextField({ id, label, value, error, hint, onChange }: Props) {
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
        onChange={(e) => onChange(e.target.value)}
      />
      {error ? (
        <span id={`${id}-note`} className="field-error" role="alert">{error}</span>
      ) : hint ? (
        <span id={`${id}-note`} className="field-hint">{hint}</span>
      ) : null}
    </div>
  );
}
