"""Persistência opcional (PostgreSQL): salvar e consultar resultados.

O núcleo (cálculo, simulação, comparação) não depende deste pacote: sem
`QSIMULADOR_DATABASE_URL` (ou `DATABASE_URL`) a API funciona como antes e as rotas
de histórico respondem 503.
"""
