"""CSV agregado por nível de carga (RF-43)."""

import pytest

from app.domain.validation.errors import InvalidDatasetError
from app.domain.validation.realdata import MAX_UPLOAD_BYTES
from app.realdata.levels import MAX_LEVELS, parse_levels

CSV = "users,avg_ms,p90_ms,throughput,error_rate\n10,80,120,40,0.01\n1,20,30,9,0\n5,35,50,30,0\n"


def test_niveis_sao_lidos_em_segundos_e_ordenados():
    r = parse_levels("n.csv", CSV)
    assert [lv.users for lv in r.levels] == [1, 5, 10]
    m = r.levels[2].metrics
    assert m.mean_response == pytest.approx(0.08) and m.p90 == pytest.approx(0.12)
    assert m.throughput == 40 and m.p_error == pytest.approx(0.01)


def test_convencoes_do_arquivo_agregado():
    m = parse_levels("n.csv", CSV).levels[2].metrics
    assert m.arrival_rate == m.throughput                         # λ̂ = X̂
    assert m.mean_in_flight == pytest.approx(40 * 0.08)           # L̂ = X̂·W̄ (Little)
    assert m.mean_users == 10 and m.samples == 0 and m.p_block == 0.0
    assert m.think_time == pytest.approx(10 / 40 - 0.08)
    for name in ("W", "throughput", "L"):
        s = m.summaries[name]
        assert s.n == 1 and s.ci_low is None and s.ci_high is None
    assert m.summaries["W"].mean == pytest.approx(0.08)


def test_sugestoes_de_calibracao_no_menor_nivel():
    r = parse_levels("n.csv", CSV)
    s = r.suggestions
    assert s.base_users == 1 and s.mu == pytest.approx(50.0) and s.mu_source == "menor_nivel"
    assert s.think_time == pytest.approx(1 / 9 - 0.02) and s.think_source == "estimado"
    assert "intervalo de confiança" in r.warnings[0]


def test_aviso_quando_o_menor_nivel_tem_varios_usuarios():
    r = parse_levels("n.csv", "users,avg_ms,throughput\n8,100,30\n16,200,40\n")
    assert any("já pode haver fila" in w for w in r.warnings)
    assert r.levels[0].metrics.p90 is None and r.levels[0].metrics.p_error == 0.0


def test_think_time_nao_positivo_nao_e_sugerido():
    r = parse_levels("n.csv", "users,avg_ms,throughput\n10,500,20\n")      # N/X = R
    assert r.suggestions.think_time is None and r.suggestions.think_source is None


def test_aceita_bytes_bom_ponto_e_virgula_e_linhas_em_branco():
    texto = "\ufeffusers;avg_ms;throughput\n1;20;9\n\n2;25;15\n"
    assert len(parse_levels("n.csv", texto.encode("utf-8")).levels) == 2


@pytest.mark.parametrize("nome,conteudo,trecho", [
    ("n.txt", CSV, ".csv"),
    ("n.csv", "", "vazio"),
    ("n.csv", "users,avg_ms\n1,20\n", "throughput"),
    ("n.csv", "users,avg_ms,throughput\n", "linhas de dados"),
    ("n.csv", "users,avg_ms,throughput\n0,20,9\n", "users"),
    ("n.csv", "users,avg_ms,throughput\n1.5,20,9\n", "users"),
    ("n.csv", "users,avg_ms,throughput\n1,0,9\n", "maiores que zero"),
    ("n.csv", "users,avg_ms,throughput\n1,abc,9\n", "Linha 2"),
    ("n.csv", "users,avg_ms,throughput\n1,nan,9\n", "finito"),
    ("n.csv", "users,avg_ms,throughput\n1,20,9\n1,25,8\n", "repetidos"),
    ("n.csv", "users,avg_ms,throughput,error_rate\n1,20,9,2\n", "fração"),
    ("n.csv", "users,avg_ms,throughput\n1,20\n", "colunas"),
])
def test_arquivos_invalidos(nome, conteudo, trecho):
    with pytest.raises(InvalidDatasetError, match=trecho) as exc:
        parse_levels(nome, conteudo)
    assert exc.value.field == "file"


def test_limites_de_tamanho_e_de_niveis():
    with pytest.raises(InvalidDatasetError, match="limite"):
        parse_levels("n.csv", b"x" * (MAX_UPLOAD_BYTES + 1))
    muitos = "users,avg_ms,throughput\n" + "".join(f"{u},10,5\n" for u in range(1, MAX_LEVELS + 2))
    with pytest.raises(InvalidDatasetError, match="mais de"):
        parse_levels("n.csv", muitos)
