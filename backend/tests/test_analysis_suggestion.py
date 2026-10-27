"""Sugestão de modelo pelo CV (Fase 13, RFC-26)."""

import pytest

from app.analysis.suggestion import suggest_from_cv


@pytest.mark.parametrize("cv,model,lab", [
    (1.0, "M/M/c", "mmc"), (0.7, "M/M/c", "mmc"), (1.3, "M/M/c", "mmc"),
    (0.0, "M/D/c", "mgc"), (0.1, "M/D/c", "mgc"),
    (0.69, "M/G/c", "mgc"), (0.3, "M/G/c", "mgc"), (1.31, "M/G/c", "mgc"), (2.5, "M/G/c", "mgc"),
])
def test_service_thresholds(cv, model, lab):
    s = suggest_from_cv(cv)
    assert (s.model, s.lab_model) == (model, lab)
    assert (s.distribution == "deterministic") == (model == "M/D/c")


def test_interarrival_only_confirms_poisson():
    assert suggest_from_cv(1.0, "interarrival").model == "M/M/c"
    for cv in (0.3, 2.0):
        s = suggest_from_cv(cv, "interarrival")
        assert s.model is None and "Poisson" in s.text
    assert "superestima" in suggest_from_cv(0.3, "interarrival").text
    assert "subestima" in suggest_from_cv(2.0, "interarrival").text


def test_text_uses_decimal_comma_and_invalid_kind_fails():
    assert "1,00" in suggest_from_cv(1.0).text
    with pytest.raises(ValueError):
        suggest_from_cv(1.0, "outro")
