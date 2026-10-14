"""Métricas empíricas conferidas à mão e propriedades de consistência."""

import pytest

from app.realdata.jmeter import parse_jtl
from app.realdata.metrics import (
    compute_metrics, rejection_mask, response_trend, split_levels, trimmed_window,
)
from examples.make_jtl import closed_levels_csv, closed_rows, open_rows, to_csv

# início (s), duração (s), sucesso, código — janela [0, 4]
EXEMPLO = (
    "timeStamp,elapsed,label,responseCode,responseMessage,success,failureMessage,allThreads\n"
    "0,2000,A,200,OK,true,,2\n"
    "1000,2000,A,200,OK,true,,2\n"
    "2000,1000,A,503,Service Unavailable,false,rejeitado,2\n"
    "3000,1000,A,200,OK,true,,2\n"
    "4000,10,A,500,Erro,false,falha,2\n"
)


def test_metricas_conferidas_a_mao():
    ds = parse_jtl(EXEMPLO)
    t0 = float(ds.start[0])
    m = compute_metrics(ds, t0, t0 + 4.0)
    assert m.samples == 5 and m.successes == 3
    assert m.rejections == 1 and m.other_failures == 1
    assert m.arrival_rate == pytest.approx(5 / 4)
    assert m.throughput == pytest.approx(3 / 4)                 # términos com sucesso em 2 s, 3 s e 4 s
    assert m.mean_response == pytest.approx((2 + 2 + 1) / 3)
    assert m.p_block == pytest.approx(1 / 5) and m.p_error == pytest.approx(1 / 5)
    # sobreposição: 2 + 2 + 1 + 1 + 0,01 (a de 4,000 s a 4,010 s encosta no fim da janela)
    assert m.mean_in_flight == pytest.approx((2 + 2 + 1 + 1 + 0.0) / 4, abs=0.01)
    assert m.mean_users == pytest.approx(2.0)


def test_rejeicao_distingue_fila_cheia_de_erro_de_aplicacao():
    ds = parse_jtl(EXEMPLO)
    assert list(rejection_mask(ds)) == [False, False, True, False, False]


def test_janela_descarta_inicio_e_fim():
    ds = parse_jtl(EXEMPLO)
    lo, hi = trimmed_window(ds, 25, 25)
    assert (lo - ds.start[0], hi - ds.start[0]) == pytest.approx((1.0, 3.0))


def test_lei_de_little_confere_com_a_concorrencia_medida():
    ds = parse_jtl(to_csv(closed_rows(20, 1.0, 10.0, 1, 300, seed=4)))
    m = split_levels(ds)[0].metrics
    assert m.mean_in_flight == pytest.approx(m.throughput * m.mean_response, rel=0.05)
    # lei do tempo de resposta interativo: N = X·(W + Z)
    assert m.mean_users == pytest.approx(m.throughput * (m.mean_response + m.think_time), rel=1e-9)


def test_intervalo_de_confianca_por_lotes_cobre_a_media():
    ds = parse_jtl(to_csv(open_rows(5, 10, 1, None, 600, seed=3)))
    m = split_levels(ds)[0].metrics
    w = m.summaries["W"]
    assert w.n == 20 and w.ci_low < m.mean_response < w.ci_high
    assert m.summaries["throughput"].ci_low < m.throughput < m.summaries["throughput"].ci_high


def test_niveis_de_carga_sao_separados_e_ordenados():
    ds = parse_jtl(closed_levels_csv([1, 5, 20], 1.0, 10.0, 1, 120, seed=2))
    levels = split_levels(ds)
    assert [lv.users for lv in levels] == [1, 5, 20]
    assert levels[0].metrics.mean_response < levels[1].metrics.mean_response < levels[2].metrics.mean_response


def test_tendencia_alta_quando_a_fila_cresce():
    ds = parse_jtl(to_csv(open_rows(15, 10, 1, None, 120, seed=1)))   # λ > μ: instável
    lo, hi = trimmed_window(ds)
    assert response_trend(ds, lo, hi) > 0.5

def test_fila_estavel_nao_gera_falso_alarme_de_tendencia():
    # ρ = 0,6: o tempo de resposta oscila, mas não cresce. Em 30 sementes quase nenhuma acusa tendência.
    alarmes = 0
    for seed in range(1, 31):
        ds = parse_jtl(to_csv(open_rows(6, 10, 1, None, 300, seed=seed)))
        lo, hi = trimmed_window(ds)
        alarmes += (response_trend(ds, lo, hi) or 0) > 0.5
    assert alarmes <= 2
