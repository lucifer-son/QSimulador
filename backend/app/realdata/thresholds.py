"""Limiares do recomendador. Todos **propostos**: calibrar com os testes reais da disciplina.

Ficam juntos, nomeados e documentados para que ajustar um critério não exija caçar números
espalhados pelo código.
"""

MIN_SAMPLES = 30                 # amostras (e sucessos) mínimas na janela
REJECTION_RELEVANT = 0.005       # p̂_block a partir do qual há rejeição relevante (0,5 %)
PLATEAU_GAIN_RATIO = 0.15        # platô: (ganho relativo de vazão) / (ganho relativo de usuários) entre os dois maiores patamares
PLATEAU_MIN_USERS_RATIO = 1.2    # os patamares precisam diferir ao menos 20 % em usuários
CV_LOW, CV_HIGH = 0.7, 1.3       # faixa em que o CV é "compatível com exponencial"
TREND_CRITICAL = 0.5             # crescimento significativo (p < 0,01) de +50 % do tempo de resposta ao longo da janela
TREND_WARNING = 0.2
TIE_PP = 5.0                     # diferença (pontos percentuais) abaixo da qual se prefere o mais simples
PARAM_PENALTY_PP = 2.0           # penalidade por parâmetro calibrado com os mesmos dados
ERROR_CAP_PCT = 100.0            # teto do erro relativo de cada métrica no escore
NO_FIT_SCORE = 60.0              # acima disso, nenhum modelo do catálogo "se ajusta"
CONF_HIGH_SCORE = 15.0
CONF_MEDIUM_SCORE = 30.0
CONF_GAP_PP = 10.0
CONF_MIN_LEVELS = 3
