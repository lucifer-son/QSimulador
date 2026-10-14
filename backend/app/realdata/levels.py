"""Importação do CSV de níveis de carga: um teste por linha, com o número de usuários.

Formato (cabeçalho obrigatório; `p90_ms` e `error_rate` são opcionais):

    users,avg_ms,p90_ms,throughput,error_rate

`avg_ms` é o tempo médio de resposta em ms, `throughput` é a vazão em req/s e
`error_rate`, a fração de falhas (0 a 1).
"""

from dataclasses import asdict, dataclass

from app.domain.validation.errors import InvalidDatasetError
from app.realdata.jmeter import check_file, number, read_table

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
class LevelsDataset:
    levels: tuple[Level, ...]    # ordenados por número de usuários

    def as_dict(self) -> dict:
        return asdict(self)


def parse_levels(filename: str, content: str) -> LevelsDataset:
    """Lê o CSV de níveis de carga. Levanta InvalidDatasetError se inválido."""
    columns, rows = read_table(check_file(filename, content), REQUIRED_COLUMNS)
    if len(rows) > MAX_LEVELS:
        raise InvalidDatasetError(f"O arquivo tem mais de {MAX_LEVELS} níveis de carga.", "file")
    levels = []
    for i, row in enumerate(rows):
        line = i + 2
        users = number(row, "users", line)
        if users < 1 or users != int(users):
            raise InvalidDatasetError(f"Linha {line}: 'users' deve ser um inteiro maior ou igual a 1.", "file")
        avg_ms = number(row, "avg_ms", line)
        throughput = number(row, "throughput", line)
        if avg_ms <= 0 or throughput <= 0:
            raise InvalidDatasetError(f"Linha {line}: 'avg_ms' e 'throughput' devem ser maiores que zero.", "file")
        p90 = number(row, "p90_ms", line) if "p90_ms" in columns and row["p90_ms"].strip() else None
        err = number(row, "error_rate", line) if "error_rate" in columns and row["error_rate"].strip() else None
        if err is not None and not 0 <= err <= 1:
            raise InvalidDatasetError(f"Linha {line}: 'error_rate' deve ser uma fração entre 0 e 1.", "file")
        levels.append(Level(int(users), avg_ms, throughput, p90, err))
    if len({lv.users for lv in levels}) != len(levels):
        raise InvalidDatasetError("Há níveis repetidos na coluna 'users'.", "file")
    return LevelsDataset(tuple(sorted(levels, key=lambda lv: lv.users)))
