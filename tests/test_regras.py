import pytest

from advisor.domain import regras


def test_pesos_de_relevancia_incompletos_falham_explicitamente():
    with pytest.raises(ValueError, match="pesos de relevância ausentes"):
        regras.validar_pesos({"outra_rota": 1.0})


def test_todas_as_chaves_de_relevancia_sao_aceitas():
    regras.validar_pesos({chave: 1.0 for chave in regras.CHAVES_RELEVANCIA})

