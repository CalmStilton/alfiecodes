# alfiecodes

A browser IDE for a young coder: [code-server](https://github.com/coder/code-server)
with Python, pygame-ce, pygbag and Pygame Zero preinstalled, plus two small tools.
Built by CI to `ghcr.io/calmstilton/alfiecodes:latest`.

- **`pgzlite.py`** is a small Pygame Zero look-alike that runs under pygbag, so a game
  written for `pgzrun` runs unchanged in a browser.
- **`publish.py`** (`publish-game` in the image) builds `projects/<game>/game.py` for the
  browser. `--play` serves it for test-play; without it, the game is added to `/published`
  and the arcade index page.
- **`workspace/.vscode/tasks.json`** gives the editor "Play my game" and "Publish my game".
- **`compose.yml`** runs it. Put `PASSWORD=...` in a `.env` file beside it.

Tests: `python -m venv .venv && .venv/bin/pip install pygame-ce numpy pytest pgzero && .venv/bin/python -m pytest tests`
(tests that use real game files skip unless `ALFIE_GAMES` points at them).
