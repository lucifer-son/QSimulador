"""Leitura e validação do CSV (JTL) do Apache JMeter.

O JTL tem uma linha por amostra. Colunas obrigatórias: `timeStamp` (início da amostra, ms
desde a época, ou data formatada), `elapsed` (ms), `label` e `success`. As demais
(`responseCode`, `responseMessage`, `failureMessage`, `allThreads`...) melhoram a análise.

Tudo o que sai daqui está em **segundos**, a unidade da interface (decisão 7).
"""

import csv
import io
import math
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from app.domain.validation.errors import InvalidDatasetError

REQUIRED_COLUMNS = ("timeStamp", "elapsed", "label", "success")
OPTIONAL_COLUMNS = ("responseCode", "responseMessage", "failureMessage", "allThreads", "threadName")

MAX_ROWS = 2_000_000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_DATE_FORMATS = ("%Y/%m/%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class JMeterDataset:
    """Amostras ordenadas pelo instante de início. Os vetores têm o mesmo tamanho."""

    start: np.ndarray            # s (época), início de cada amostra
    elapsed: np.ndarray          # s, tempo de resposta
    success: np.ndarray          # bool
    label: np.ndarray            # str
    response_code: np.ndarray | None
    response_message: np.ndarray | None
    failure_message: np.ndarray | None
    all_threads: np.ndarray | None   # int, usuários ativos quando a amostra terminou

    @property
    def end(self) -> np.ndarray:
        return self.start + self.elapsed

    def __len__(self) -> int:
        return int(self.start.size)

    def select(self, mask: np.ndarray) -> "JMeterDataset":
        def pick(a: np.ndarray | None) -> np.ndarray | None:
            return None if a is None else a[mask]

        return JMeterDataset(
            self.start[mask], self.elapsed[mask], self.success[mask], self.label[mask],
            pick(self.response_code), pick(self.response_message),
            pick(self.failure_message), pick(self.all_threads),
        )


@dataclass(frozen=True)
class JMeterSummary:
    samples_total: int
    samples_used: int
    label: str | None
    include_failures: bool
    trim_start_s: float
    trim_end_s: float
    window_seconds: float
    throughput: float
    mean_ms: float
    std_ms: float
    min_ms: float
    max_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    error_rate: float
    users: int | None
    users_max: int | None
    suggested_mu: float
    labels: list[dict]

    def as_dict(self) -> dict:
        return asdict(self)


def check_file(filename: str, content: str | bytes) -> str:
    """Valida o nome e o tamanho de um CSV antes de o analisar."""
    from app.domain.validation.errors import InvalidDatasetError

    if not filename.lower().endswith(".csv"):
        raise InvalidDatasetError("Envie um arquivo com extensão .csv.", "file")
    raw = content.encode("utf-8") if isinstance(content, str) else content
    if len(raw) > MAX_UPLOAD_BYTES:
        raise InvalidDatasetError("O arquivo passa do limite de 10 MB.", "file")
    if not raw.strip():
        raise InvalidDatasetError("O arquivo está vazio.", "file")
    return _decode(raw)


def read_table(content: str, required: tuple[str, ...] = ()) -> tuple[list[str], list[dict[str, str]]]:
    """Lê um CSV genérico com cabeçalho, usado também pelo formato agregado."""
    from app.domain.validation.errors import InvalidDatasetError

    lines = content.splitlines()
    if not lines:
        raise InvalidDatasetError("O arquivo está vazio.", "file")
    reader = csv.DictReader(io.StringIO(content), delimiter=_delimiter(lines[0]))
    columns = [name.strip() for name in (reader.fieldnames or [])]
    mapping = {name.lower(): name for name in columns}
    missing = [name for name in required if name.lower() not in mapping]
    if missing:
        raise InvalidDatasetError(f"Colunas obrigatórias ausentes: {', '.join(missing)}.", "file")
    rows = [{str(k).strip(): (v or "").strip() for k, v in row.items() if k is not None}
            for row in reader]
    return columns, rows


def number(row: dict[str, str], column: str, line: int) -> float:
    from app.domain.validation.errors import InvalidDatasetError

    try:
        value = float(row[column])
    except (KeyError, ValueError):
        raise InvalidDatasetError(f"Linha {line}: '{column}' deve ser numérico.", "file") from None
    if not math.isfinite(value):
        raise InvalidDatasetError(f"Linha {line}: '{column}' deve ser finito.", "file")
    return value


def _decode(content: bytes | str) -> str:
    if isinstance(content, str):
        return content.lstrip("\ufeff")
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InvalidDatasetError("Não foi possível ler o arquivo como texto.", "file")


def _delimiter(header_line: str) -> str:
    return ";" if header_line.count(";") > header_line.count(",") else ","


def _timestamp(value: str, row: int) -> float:
    text = value.strip()
    try:
        return float(text) / 1000.0
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            # Data formatada pelo JMeter não traz fuso: usa-se UTC, só importam as diferenças.
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    raise InvalidDatasetError(f"Linha {row}: timeStamp inválido ({text!r}).", "file")


def _success(value: str, row: int) -> bool:
    text = value.strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise InvalidDatasetError(f"Linha {row}: success deve ser true ou false (veio {value!r}).", "file")


def _elapsed(value: str, row: int) -> float:
    try:
        number = float(value)
    except ValueError:
        raise InvalidDatasetError(f"Linha {row}: elapsed não numérico ({value!r}).", "file") from None
    if not np.isfinite(number) or number < 0:
        raise InvalidDatasetError(f"Linha {row}: elapsed deve ser um número não negativo.", "file")
    return number / 1000.0


def parse_jtl(content: bytes | str) -> JMeterDataset:
    """Lê um JTL em CSV. Levanta InvalidDatasetError (campo `file`) se o arquivo não servir."""
    text = _decode(content)
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        raise InvalidDatasetError("O arquivo está vazio.", "file")

    reader = csv.reader(io.StringIO(text), delimiter=_delimiter(lines[0]))
    header = [h.strip() for h in next(reader)]
    index = {name.lower(): i for i, name in enumerate(header)}

    missing = [c for c in REQUIRED_COLUMNS if c.lower() not in index]
    if missing:
        raise InvalidDatasetError(
            f"Colunas obrigatórias ausentes: {', '.join(missing)}. O JTL precisa de cabeçalho "
            f"com {', '.join(REQUIRED_COLUMNS)} (no JMeter, ative 'Save field names').",
            "file",
        )
    col = {name: index[name.lower()] for name in (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS) if name.lower() in index}

    starts, elapsed, success, labels = [], [], [], []
    optional: dict[str, list] = {name: [] for name in OPTIONAL_COLUMNS if name in col}
    width = len(header)

    for row_number, row in enumerate(reader, start=2):
        if not row:
            continue
        if len(row) < width:
            raise InvalidDatasetError(f"Linha {row_number}: faltam colunas ({len(row)} de {width}).", "file")
        if len(starts) >= MAX_ROWS:
            raise InvalidDatasetError(f"O arquivo tem mais de {MAX_ROWS:,} amostras.".replace(",", "."), "file")
        starts.append(_timestamp(row[col["timeStamp"]], row_number))
        elapsed.append(_elapsed(row[col["elapsed"]], row_number))
        success.append(_success(row[col["success"]], row_number))
        labels.append(row[col["label"]])
        for name, values in optional.items():
            raw = row[col[name]]
            if name == "allThreads":
                try:
                    values.append(int(float(raw)))
                except ValueError:
                    raise InvalidDatasetError(
                        f"Linha {row_number}: allThreads não numérico ({raw!r}).", "file"
                    ) from None
            else:
                values.append(raw)

    if not starts:
        raise InvalidDatasetError("O arquivo não tem nenhuma amostra além do cabeçalho.", "file")

    order = np.argsort(np.asarray(starts), kind="stable")

    def vec(values: list | None, dtype=None) -> np.ndarray | None:
        if values is None:
            return None
        return np.asarray(values, dtype=dtype)[order]

    return JMeterDataset(
        start=vec(starts, float), elapsed=vec(elapsed, float), success=vec(success, bool),
        label=vec(labels, object),
        response_code=vec(optional.get("responseCode"), object),
        response_message=vec(optional.get("responseMessage"), object),
        failure_message=vec(optional.get("failureMessage"), object),
        all_threads=vec(optional.get("allThreads"), int),
    )


def summarize_jmeter(
    filename: str,
    content: str | bytes,
    label: str | None = None,
    trim_start_s: float = 0.0,
    trim_end_s: float = 0.0,
    include_failures: bool = False,
) -> JMeterSummary:
    """Resumo agregado compatível com o formato legado de relatório experimental."""
    from app.domain.validation.errors import InvalidDatasetError

    dataset = parse_jtl(check_file(filename, content))
    if label is not None:
        selected_labels = dataset.label == label
        if not np.any(selected_labels):
            raise InvalidDatasetError(f"O rótulo '{label}' não existe no arquivo.", "label")
        dataset = dataset.select(selected_labels)

    start = float(np.min(dataset.start))
    end = float(np.max(dataset.end))
    window_start = start + float(trim_start_s)
    window_end = end - float(trim_end_s)
    duration = window_end - window_start
    if duration <= 0:
        raise InvalidDatasetError("A janela de análise deve ter duração positiva.", "file")
    mask = (dataset.start >= window_start) & (dataset.end <= window_end)
    sample_count = int(np.count_nonzero(mask))
    if sample_count == 0:
        raise InvalidDatasetError("A janela não contém amostras.", "file")
    ok = dataset.success[mask]
    all_elapsed = dataset.elapsed[mask]
    usable = np.ones(sample_count, dtype=bool) if include_failures else ok
    elapsed = all_elapsed[usable]
    if elapsed.size == 0:
        raise InvalidDatasetError("Não há amostras válidas na janela.", "file")
    elapsed_ms = elapsed * 1000.0
    threads = dataset.all_threads[mask] if dataset.all_threads is not None else None
    users = int(np.median(threads)) if threads is not None else None
    labels_out = []
    for item in sorted(set(dataset.label[mask].tolist())):
        label_mask = mask & (dataset.label == item)
        label_ok = dataset.success[label_mask]
        values = dataset.elapsed[label_mask][np.ones(label_ok.size, dtype=bool) if include_failures else label_ok] * 1000.0
        if values.size:
            labels_out.append({
                "label": str(item), "samples": int(values.size),
                "mean_ms": float(np.mean(values)), "p90_ms": float(np.percentile(values, 90)),
                "error_rate": float(np.mean(~label_ok)),
            })
    return JMeterSummary(
        samples_total=len(dataset), samples_used=int(elapsed.size), label=label,
        include_failures=include_failures, trim_start_s=float(trim_start_s), trim_end_s=float(trim_end_s),
        window_seconds=duration, throughput=float(np.count_nonzero(ok) / duration),
        mean_ms=float(np.mean(elapsed_ms)), std_ms=float(np.std(elapsed_ms, ddof=1)) if elapsed_ms.size > 1 else 0.0,
        min_ms=float(np.min(elapsed_ms)), max_ms=float(np.max(elapsed_ms)),
        p50_ms=float(np.percentile(elapsed_ms, 50)), p90_ms=float(np.percentile(elapsed_ms, 90)),
        p95_ms=float(np.percentile(elapsed_ms, 95)), p99_ms=float(np.percentile(elapsed_ms, 99)),
        error_rate=float(np.mean(~ok)), users=users,
        users_max=int(np.max(threads)) if threads is not None else None,
        suggested_mu=float(1000.0 / np.mean(elapsed_ms)), labels=labels_out,
    )
