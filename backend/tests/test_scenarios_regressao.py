"""Guarda de regressão: as simulações das fases anteriores não podem mudar com a Fase 12.

A comparação de cenários ganhou um parâmetro opcional no motor (`service_at_arrival`). Estes testes
fixam, com semente, os resultados exatos de cada réplica de M/M/c, M/M/c/K, M/G/1 e M/G/c,
gravados com o código de ANTES da alteração. É a única exceção ao estilo "nunca valores exatos
de números aleatórios": aqui o objetivo é justamente provar que o refator não mexeu em nada.
"""

import pytest

from app.domain.service.distributions import build_distribution
from app.simulation.mg1 import simulate_mg1
from app.simulation.mgc import simulate_mgc
from app.simulation.mmck import simulate_mmck

# (L, Lq, W, Wq, rho, p0, throughput, p_wait, p_block, clientes medidos)
MMC = [
        (10.374327358057153, 2.1747391383126726, 1.2957226539378324, 0.2731646386596094, 0.8199588219744464, 0.0, 8.005555555555556, 0.43435754189944137, 0.0, 1425),
        (9.749946203880494, 1.604209667230172, 1.184083635203904, 0.19565176368370224, 0.814573653665029, 0.0, 8.188888888888888, 0.42375168690958165, 0.0, 1468),
        (10.379061157862147, 2.274012824719401, 1.2942710565128392, 0.2865789558254936, 0.8105048333142716, 0.0, 8.0, 0.4371508379888268, 0.0, 1423),
    ]

MMCK = [
        (5.395396001075831, 3.4056591247587544, 2.8126204411337654, 1.788652415278956, 0.9948684381585363, 0.00046831267765112567, 1.9, 0.9823529411764705, 0.6087456846950517, 336),
        (5.423316781821009, 3.4275039886801375, 2.700859885765057, 1.7135929194575779, 0.9979063965704338, 0.0, 2.0, 0.9889196675900277, 0.6147278548559232, 355),
        (5.0837289579148095, 3.1122094469662533, 2.391312965321973, 1.4706856642419688, 0.9857597554742799, 0.00700220066110791, 2.1222222222222222, 0.9660574412532638, 0.552046783625731, 379),
    ]

# (L, Lq, W, Wq, rho, p0, throughput, clientes medidos)
MG1 = [
        (1.1530275150340665, 0.6869729010661615, 0.23661057398334356, 0.1409955724273396, 0.4660546139679052, 0.5339453860320948, 4.872222222222222, 877),
        (2.7464228153577954, 2.176476712697626, 0.5290145984104213, 0.41786699721028925, 0.56994610266017, 0.43005389733983007, 5.038888888888889, 899),
        (1.0153311971944008, 0.5395501448896963, 0.20787680912324366, 0.10967769151900851, 0.4757810523047045, 0.5242189476952954, 4.833333333333333, 863),
    ]

MGC = [
        (3.945730235791395, 2.490104971777987, 0.2749205428453794, 0.17352647886954534, 0.727812632006705, 0.16105142790242377, 14.355555555555556, 0.6222910216718266, 0.0, 2583),
        (7.2192071443226435, 5.609593161799755, 0.47349982501218113, 0.3680766372890523, 0.8048069912614573, 0.1103997266283603, 15.238888888888889, 0.7145461173897193, 0.0, 2736),
        (3.112310707237016, 1.6697283882788574, 0.2116463380834172, 0.11358675280450967, 0.721291159479082, 0.16687206041329247, 14.705555555555556, 0.6138165345413363, 0.0, 2646),
    ]


def _queue(run):
    return (run.L, run.Lq, run.W, run.Wq, run.rho, run.p0, run.throughput,
            run.p_wait, run.p_block, run.measured_customers)


def _mg1(run):
    return (run.L, run.Lq, run.W, run.Wq, run.rho, run.p0, run.throughput, run.measured_customers)


def _same(actual, expected):
    assert len(actual) == len(expected)
    for got, want in zip(actual, expected):
        assert got == pytest.approx(want, rel=0, abs=0)


def test_mmc_igual_ao_anterior():
    runs = simulate_mmck(8.0, 1.0, 10, None, 200.0, 3, 20.0, 7, 0.95).runs
    for run, want in zip(runs, MMC):
        _same(_queue(run), want)


def test_mmck_igual_ao_anterior():
    runs = simulate_mmck(5.0, 1.0, 2, 6, 200.0, 3, 20.0, 7, 0.95).runs
    for run, want in zip(runs, MMCK):
        _same(_queue(run), want)


def test_mg1_igual_ao_anterior():
    service = build_distribution("lognormal", {"mean": 0.1, "cv": 1.5})
    runs = simulate_mg1(5.0, service, 200.0, 3, 20.0, 7, 0.95).runs
    for run, want in zip(runs, MG1):
        _same(_mg1(run), want)


def test_mgc_igual_ao_anterior():
    service = build_distribution("lognormal", {"mean": 0.1, "cv": 1.5})
    runs = simulate_mgc(15.0, service, 2, 200.0, 3, 20.0, 7, 0.95).runs
    for run, want in zip(runs, MGC):
        _same(_queue(run), want)
