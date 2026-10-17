"""Leitura e validação do CSV (JTL) do Apache JMeter.

O JTL tem uma linha por amostra. Colunas obrigatórias: `timeStamp` (início da amostra, ms
desde a época, ou data formatada), `elapsed` (ms), `label` e `success`. As demais
(`responseCode`, `responseMessage`, `failureMessage`, `allThreads`...) melhoram a análise.

Tudo o que sai daqui está em **segundos**, a unidade da interface (decisão 7).
"""

import csv
import io
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import numpy as np

from app.domain.validation.errors import InvalidDatasetError
from app.domain.validation.realdata import MAX_UPLOAD_BYTES

REQUIRED_COLUMNS = ("timeStamp", "elapsed", "label", "success")
OPTIONAL_COLUMNS = ("responseCode", "responseMessage", "failureMessage", "allThreads", "threadName")

MAX_ROWS = 2_000_000
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
    """Resumo de uma janela do JTL, com tempo de resposta em milissegundos."""

    samples_total: int
    samples_used: int
    label: str | None
    include_failures: bool
    trim_start_s: float
    trim_end_s: float
    window_seconds: float
    throughput: float
    mean_ms: float
    users: int | None
    users_max: int | None

    def as_dict(self) -> dict:
        return asdict(self)


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
    content: bytes | str,
    label: str | None = None,
    trim_start_s: float = 0.0,
    trim_end_s: float = 0.0,
    include_failures: bool = False,
) -> JMeterSummary:
    """Valida e resume um JTL em uma janela, descartando aquecimento e encerramento."""
    from app.realdata.metrics import compute_metrics

    if not filename.lower().endswith(".csv"):
        raise InvalidDatasetError("Envie um arquivo com extensão .csv.", "file")
    size = len(content.encode("utf-8")) if isinstance(content, str) else len(content)
    if size > MAX_UPLOAD_BYTES:
        raise InvalidDatasetError(
            f"O arquivo passa do limite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", "file"
        )
    for name, value in (("trim_start_s", trim_start_s), ("trim_end_s", trim_end_s)):
        if not np.isfinite(value) or value < 0:
            raise InvalidDatasetError(f"{name} deve ser um número não negativo.", name)

    dataset = parse_jtl(content)
    samples_total = len(dataset)
    if label is not None:
        dataset = dataset.select(dataset.label == label)
        if len(dataset) == 0:
            raise InvalidDatasetError(f"O rótulo {label!r} não foi encontrado no arquivo.", "label")

    start, end = float(dataset.start[0]), float(dataset.end.max())
    window_start, window_end = start + trim_start_s, end - trim_end_s
    if window_end <= window_start:
        raise InvalidDatasetError("Os intervalos descartados deixam uma janela sem duração.", "file")

    in_window = (dataset.start >= window_start) & (dataset.start <= window_end)
    if not include_failures:
        in_window &= dataset.success
    used = dataset.select(in_window)
    if len(used) == 0:
        raise InvalidDatasetError("Não há amostras na janela selecionada.", "file")

    metrics = compute_metrics(dataset, window_start, window_end)
    response_samples = used.elapsed if include_failures else used.elapsed[used.success]
    if response_samples.size == 0:
        raise InvalidDatasetError("Não há amostras bem-sucedidas na janela selecionada.", "file")

    users = None if metrics.mean_users is None else int(round(metrics.mean_users))
    users_max = None
    if dataset.all_threads is not None:
        user_window = (dataset.end >= window_start) & (dataset.end <= window_end)
        if user_window.any():
            users_max = int(dataset.all_threads[user_window].max())

    return JMeterSummary(
        samples_total=samples_total, samples_used=len(used), label=label,
        include_failures=include_failures, trim_start_s=trim_start_s, trim_end_s=trim_end_s,
        window_seconds=window_end - window_start, throughput=metrics.throughput,
        mean_ms=float(response_samples.mean() * 1000), users=users, users_max=users_max,
    )
