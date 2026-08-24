from advisor.client import game_client
from advisor.data import ddragon
from advisor.domain.draft import Draft


static = ddragon.load()


class Resposta:
    def __init__(self, corpo, ok=True):
        self.corpo = corpo
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise game_client.requests.HTTPError("indisponível")

    def json(self):
        return self.corpo


def _jogador(nome, posicao, time):
    return {"championName": nome, "position": posicao, "team": time}


def _draft():
    nomes = ["Jinx", "Nautilus", "LeeSin", "Ahri", "Ornn"]
    return Draft(
        champion=static.champion("Lucian"), lane="bottom",
        enemies=[static.champion(nome) for nome in nomes])


def test_confirma_as_cinco_rotas_e_o_oponente_direto():
    jogadores = [
        _jogador("Lucian", "BOTTOM", "ORDER"),
        _jogador("Nami", "SUPPORT", "ORDER"),
        _jogador("Garen", "TOP", "ORDER"),
        _jogador("Vi", "JUNGLE", "ORDER"),
        _jogador("Syndra", "MIDDLE", "ORDER"),
        _jogador("Jinx", "BOTTOM", "CHAOS"),
        _jogador("Nautilus", "SUPPORT", "CHAOS"),
        _jogador("LeeSin", "JUNGLE", "CHAOS"),
        _jogador("Ahri", "MIDDLE", "CHAOS"),
        _jogador("Ornn", "TOP", "CHAOS"),
    ]

    confirmado = game_client.confirmar_rotas(
        _draft(), static, buscar=lambda *a, **k: Resposta(jogadores))

    assert confirmado is not None and confirmado.rotas_confirmadas
    assert confirmado.opponent.name == "Jinx"
    assert confirmado.rotas_inimigas[static.champion("Nautilus").cid] == "support"
    assert set(confirmado.rotas_inimigas.values()) == {
        "top", "jungle", "middle", "bottom", "support"}


def test_lista_incompleta_ainda_nao_confirma():
    jogadores = [_jogador("Lucian", "BOTTOM", "ORDER")]
    assert game_client.confirmar_rotas(
        _draft(), static,
        buscar=lambda *a, **k: Resposta(jogadores)) is None

