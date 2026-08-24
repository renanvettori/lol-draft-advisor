# LoL Draft Advisor

A Python tool that reads a League of Legends draft, compares all five enemy
matchups, and suggests runes, summoner spells, and item changes before the game
starts.

[![Tests](https://github.com/renanvettori/lol-draft-advisor/actions/workflows/tests.yml/badge.svg)](https://github.com/renanvettori/lol-draft-advisor/actions/workflows/tests.yml)

> Personal data analysis and automation project. It is not affiliated with
> Riot Games, League of Legends, or Lolalytics.

## Why this exists

Most build sites show what players usually buy. That is useful, but it does not
answer what to do when all five enemies are already known.

I built this tool to make that part less manual. It collects the matchup data,
checks how reliable each signal is, and turns the result into something that can
be read before the game starts.

## What it does

The advisor reads champion select through the local League Client API, fetches
the champion's base build and five matchup pages, and shows:

- runes and summoner spells during champion select;
- a preview of the popular item build;
- the final item sequence after the loading screen confirms enemy routes;
- a local HTML report with the recommendation and the numbers behind it;
- optional automatic application of runes and spells, with Flash placed on D.

The result is a starting point, not a promise of a higher win rate. It puts
several imperfect signals in one place so the player can make a quicker choice.

## What I had to get right

### Matchup aggregation

The tool fetches each enemy matchup once and combines the five observations using
route relevance. When the player is support, the enemy ADC also counts as a
same-lane opponent. Otherwise the enemy support would receive all of that lane's
weight.

### Different evidence for different decisions

Runes and summoner spells are chosen before the game starts, so matchup win rate
is useful for those decisions. Items are bought after the game has developed. A
defensive item may be a response to losing rather than the reason someone lost.
The item path therefore starts from the popular Emerald+ build and adapts using
pick rate instead of item win rate.

### When the data is weak

The code checks sample size, compares choices inside each matchup, weighs route
relevance, and corrects for multiple comparisons. If the data does not support
an item change, the popular build stays on screen.

## Architecture

```text
League Client / local game API
              │
              ▼
      advisor.client + advisor.data
              │  fetch, cache, parse and normalize
              ▼
        advisor.domain
              │  draft, comparisons and recommendation contracts
              ▼
        advisor.fluxos
              │  snapshot, route confirmation and application
              ▼
      advisor.apresentacao
              ├── concise terminal output
              └── local HTML report
```

The domain does not perform HTTP, print output, or write to the League Client.
External data enters through an adapter seam, and all client writes live in
`advisor/client/perks.py`.

The [architecture guide](docs/guia.md) has the package boundaries and the main
maintenance rules.

## Example output

Open the [live HTML recommendation report](https://renanvettori.github.io/lol-draft-advisor/assets/ultima-recomendacao.html)
or the [local HTML file](docs/assets/ultima-recomendacao.html). It contains the
full page: runes, spells, item path, and calculation details.

The example is sanitized. It contains no player identifiers, session captures,
logs, or account data.

## Running locally

The normal entry point is `advisor.bat`, which keeps the watcher open while you
play. The live workflow expects Python 3.13 and a running League Client.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Start the live workflow with:

```powershell
.\.venv\Scripts\python.exe -m advisor --vigiar
```

Permanent preferences live in [`config.toml`](config.toml).

## Limitations

- The League Client API is local and unsupported by Riot. Its behavior can
  change without notice.
- Lolalytics can change its serialized page structure or restrict requests.
- Enemy routes are inferred during champion select and replaced by confirmed
  routes only for the final item sequence.
- The project has not established a causal increase in win rate.
- The current version works before the game. An in-game recommendation mode is
  still a future experiment.

## Development

Tests run without League Client access by using in-memory data sources:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The GitHub Actions workflow runs the same test suite on every push and pull
request.

## License and third-party material

The source code is released under the [MIT License](LICENSE). League of Legends
names, images, game data, and Lolalytics data remain subject to their respective
owners' terms. This repository does not include captured sessions, account
credentials, or a production API key.

---

## Português

### O problema

A maioria dos sites de build mostra o que os jogadores costumam comprar. Isso
ajuda, mas não responde totalmente ao que fazer quando os cinco inimigos já
estão definidos.

O LoL Draft Advisor combina os cinco matchups, considera a relevância das rotas
e transforma esses dados em uma recomendação de runas, feitiços e itens.

### As decisões técnicas

Runas e feitiços usam comparação pareada e win rate de matchup. Itens partem da
build popular e usam pick rate, porque uma compra defensiva pode ser reação a
uma partida ruim. Quando a amostra é fraca, a ferramenta mantém a build popular
em vez de forçar uma troca.

O projeto é uma aplicação de análise de dados e automação em Python. Ele não
promete garantir vitórias.

