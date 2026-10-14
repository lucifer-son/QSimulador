"""Leitura e validação do CSV (JTL) do JMeter."""

import pytest

from app.domain.validation.errors import InvalidDatasetError
from app.realdata.jmeter import parse_jtl

HEADER = "timeStamp,elapsed,label,responseCode,responseMessage,success,failureMessage,allThreads"


def jtl(*rows: str, header: str = HEADER) -> str:
    return "\n".join([header, *rows]) + "\n"


VALIDO = jtl(
    "1760000002000,500,B,200,OK,true,,5",
    "1760000000000,250,A,200,OK,true,,5",
    "1760000001000,1000,A,503,Service Unavailable,false,rejeitado,5",
)


def test_le_converte_unidades_e_ordena_por_inicio():
    ds = parse_jtl(VALIDO)
    assert len(ds) == 3
    assert list(ds.start - ds.start[0]) == pytest.approx([0.0, 1.0, 2.0])
    assert list(ds.elapsed) == pytest.approx([0.25, 1.0, 0.5])   # ms -> s
    assert list(ds.success) == [True, False, True]
    assert list(ds.label) == ["A", "A", "B"]
    assert list(ds.all_threads) == [5, 5, 5]
    assert list(ds.end - ds.start) == pytest.approx(list(ds.elapsed))


def test_aceita_bom_ponto_e_virgula_e_success_em_qualquer_caixa():
    texto = "\ufeff" + VALIDO.replace(",", ";").replace("TRUE", "true")
    texto = texto.replace(";true;", ";TRUE;").replace(";false;", ";False;")
    ds = parse_jtl(texto.encode("utf-8"))
    assert len(ds) == 3 and list(ds.success) == [True, False, True]


def test_aceita_data_formatada_no_timestamp():
    ds = parse_jtl(jtl("2026/10/13 10:00:01.500,100,A,200,OK,true,,1",
                       "2026/10/13 10:00:00.000,100,A,200,OK,true,,1"))
    assert ds.start[1] - ds.start[0] == pytest.approx(1.5)


def test_colunas_opcionais_podem_faltar():
    ds = parse_jtl("timeStamp,elapsed,label,success\n1000,10,A,true\n")
    assert ds.all_threads is None and ds.response_code is None


@pytest.mark.parametrize(
    "conteudo, trecho",
    [
        ("", "vazio"),
        ("timeStamp,elapsed,label,success\n", "nenhuma amostra"),
        ("elapsed,label,success\n10,A,true\n", "timeStamp"),                       # sem cabeçalho de verdade
        ("1760000000000,10,A,true\n1760000001000,10,A,true\n", "Colunas obrigatórias"),
        ("timeStamp,elapsed,label,success\n1000,abc,A,true\n", "elapsed não numérico"),
        ("timeStamp,elapsed,label,success\n1000,-5,A,true\n", "não negativo"),
        ("timeStamp,elapsed,label,success\n1000,10,A,talvez\n", "true ou false"),
        ("timeStamp,elapsed,label,success\nontem,10,A,true\n", "timeStamp inválido"),
        ("timeStamp,elapsed,label,success\n1000,10\n", "faltam colunas"),
        ("timeStamp,elapsed,label,success,allThreads\n1000,10,A,true,muitos\n", "allThreads"),
    ],
)
def test_arquivos_invalidos_sao_rejeitados_com_o_campo_file(conteudo, trecho):
    with pytest.raises(InvalidDatasetError) as erro:
        parse_jtl(conteudo)
    assert erro.value.field == "file"
    assert trecho.lower() in str(erro.value).lower()
