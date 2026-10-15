"""Importação do CSV agregado por nível de carga (RF-43): um teste por linha.

Formato (cabeçalho obrigatório; `p90_ms` e `error_rate` são opcionais):

    users,avg_ms,p90_ms,throughput,error_rate

`avg_ms` é o tempo médio de resposta em ms, `throughput` é a vazão em req/s e `error_rate`,
a fração de falhas (0 a 1). Cada linha vira um `LoadLevel`, o mesmo objeto que a análise do JTL
produz, e por isso alimenta a comparação com o modelo sem nenhum código especial.

O que o arquivo agregado **não** traz é preenchido pela convenção abaixo e sinalizado:
- λ̂ (taxa de chegada) = X̂, o que vale sem rejeições;
- L̂ = X̂·W̄ (lei de Little), derivado e não medido;
- sem amostras, não há intervalo de confiança do medido (n = 1).
"""

import csv
import io
import math
from dataclasses import dataclass, field

from app.domain.validation.errors import InvalidDatasetError
from app.domain.validation.realdata import MAX_UPLOAD_BYTES
from app.realdata.metrics import EmpiricalMetrics, LoadLevel
from app.simulation.results import MetricSummary

REQUIRED_COLUMNS = ("users", "avg_ms", "throughput")
MAX_LEVELS = 50


@dataclass(frozen=True)
class Level:
    users: int
    avg_ms: float
    throughput: float
    p90_ms: float | None = None
    error_rate: float | None = None


@dataclass(frozen=True)
class LevelSuggestions:
    """Calibração sugerida a partir do menor nível de carga (o usuário pode trocar os valores)."""

    mu: float | None                 # 1/R no menor nível (só vale sem fila, N ≤ c)
    mu_source: str                   # sempre "menor_nivel"
    think_time: float | None         # Z = N/X − R no menor nível (None se não for positivo)
    think_source: str | None         # "estimado" ou None
    base_users: int


@dataclass(frozen=True)
class LevelsImport:
    levels: list[LoadLevel]
    suggestions: LevelSuggestions
    warnings: list[str] = field(default_factory=list)


def _fail(message: str, field_name: str = "file") -> InvalidDatasetError:
    return InvalidDatasetError(message, field_name)


def _decode(content: bytes | str) -> str:
    if isinstance(content, str):
        return content.lstrip("\ufeff")
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise _fail("Não foi possível ler o arquivo como texto.")


def _number(row: dict[str, str], column: str, line: int) -> float:
    try:
        value = float(row[column])
    except ValueError:
        raise _fail(f"Linha {line}: valor inválido em '{column}' ({row[column]!r}).") from None
    if not math.isfinite(value):
        raise _fail(f"Linha {line}: valor não finito em '{column}'.")
    return value


def _empirical(users: int, avg_s: float, throughput: float, p90_s: float | None, error: float) -> EmpiricalMetrics:
    one = lambda v: MetricSummary(mean=v, std=None, ci_low=None, ci_high=None, n=1)  # noqa: E731
    z = users / throughput - avg_s
    return EmpiricalMetrics(
        window_start=0.0, window_end=0.0, duration=0.0,
        samples=0, successes=0, rejections=0, other_failures=0,
        arrival_rate=throughput, throughput=throughput, mean_response=avg_s,
        p50=None, p90=p90_s, p95=None, p99=None,           # type: ignore[arg-type]
        mean_in_flight=throughput * avg_s, peak_in_flight=0,
        mean_users=float(users), think_time=z if z > 0 else None,
        p_block=0.0, p_error=error, arrival_cv=None, response_cv=None,
        summaries={"W": one(avg_s), "throughput": one(throughput), "L": one(throughput * avg_s)},
    )


def parse_levels(filename: str, content: bytes | str) -> LevelsImport:
    """Lê o CSV agregado. Levanta InvalidDatasetError se o arquivo for inválido."""
    if not filename.lower().endswith(".csv"):
        raise _fail("Envie um arquivo com extensão .csv.")
    size = len(content.encode("utf-8")) if isinstance(content, str) else len(content)
    if size > MAX_UPLOAD_BYTES:
        raise _fail(f"O arquivo passa do limite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    text = _decode(content)
    if not text.strip():
        raise _fail("O arquivo está vazio.")

    header = text.lstrip().splitlines()[0]
    delimiter = max((",", ";", "\t"), key=header.count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    columns = [c.strip() for c in (reader.fieldnames or [])]
    reader.fieldnames = columns
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise _fail(f"Colunas obrigatórias ausentes: {', '.join(missing)}. Colunas encontradas: {', '.join(columns) or 'nenhuma'}.")

    parsed = []
    try:
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise _fail(f"Linha {reader.line_num}: número de colunas diferente do cabeçalho.")
            if not any(v.strip() for v in row.values()):
                continue
            line = reader.line_num
            users = _number(row, "users", line)
            if users < 1 or users != int(users):
                raise _fail(f"Linha {line}: 'users' deve ser um inteiro maior ou igual a 1.")
            avg_ms = _number(row, "avg_ms", line)
            throughput = _number(row, "throughput", line)
            if avg_ms <= 0 or throughput <= 0:
                raise _fail(f"Linha {line}: 'avg_ms' e 'throughput' devem ser maiores que zero.")
            p90 = _number(row, "p90_ms", line) if "p90_ms" in columns and row["p90_ms"].strip() else None
            err = _number(row, "error_rate", line) if "error_rate" in columns and row["error_rate"].strip() else 0.0
            if not 0 <= err <= 1:
                raise _fail(f"Linha {line}: 'error_rate' deve ser uma fração entre 0 e 1.")
            parsed.append((int(users), avg_ms / 1000.0, throughput, None if p90 is None else p90 / 1000.0, err))
    except csv.Error as exc:
        raise _fail(f"CSV malformado: {exc}") from exc
    if not parsed:
        raise _fail("O arquivo não tem linhas de dados.")
    if len(parsed) > MAX_LEVELS:
        raise _fail(f"O arquivo tem mais de {MAX_LEVELS} níveis de carga.")
    if len({p[0] for p in parsed}) != len(parsed):
        raise _fail("Há níveis repetidos na coluna 'users'.")

    parsed.sort(key=lambda p: p[0])
    levels = [LoadLevel(u, _empirical(u, w, x, p90, e)) for u, w, x, p90, e in parsed]
    base = levels[0]
    w0, x0 = base.metrics.mean_response, base.metrics.throughput
    warnings = [
        "Arquivo agregado: λ̂ foi tomado como igual à vazão X̂ (vale sem rejeições) e L̂ = X̂·W̄ é derivado pela lei de Little. "
        "Não há intervalo de confiança do medido."
    ]
    if base.users and base.users > 1:
        warnings.append(
            f"O menor nível tem {base.users} usuários: já pode haver fila nele, então μ = 1/R fica subestimado. "
            "Informe o tempo de serviço, se o conhecer."
        )
    return LevelsImport(
        levels=levels,
        suggestions=LevelSuggestions(
            mu=1.0 / w0, mu_source="menor_nivel",
            think_time=base.metrics.think_time, think_source="estimado" if base.metrics.think_time else None,
            base_users=base.users or 0,
        ),
        warnings=warnings,
    )
