# alfiecodes

A browser IDE for a young coder: [code-server](https://github.com/coder/code-server)
with Python, pygame-ce, pygbag and Pygame Zero preinstalled, plus two small tools.
Built by CI to `ghcr.io/calmstilton/alfiecodes:latest`.

- **`pgzlite.py`** is a small Pygame Zero look-alike that runs under pygbag, so a game
  written for `pgzrun` runs unchanged in a browser.
- **`publish.py`** (`publish` in the image) builds `projects/<project>` for the browser:
  a Pygame Zero `game.py` through pgzlite and pygbag, or a website (`index.html`) copied as it is. Anything else is refused with an explanation. `--run` serves it for a try-out; without it, the project is added to `/published`
  and the projects index page.
- **`workspace/`** is the starting workspace: `.vscode/tasks.json` gives the editor "Run my project" (F5), "Publish my project" (F6) and a Help button that opens `HELP.md`; `README.md` is the front page of the projects repo.
- **`autosave.sh`** (`autosave` in the image) commits and pushes the workspace if it is a git repo; `lxc/` has the systemd units for the LXC: the autosave timer (nightly, 7pm UK time) and an image update timer (Mondays 5:30am UK time, after CI's weekly rebuild). The LXC also runs Debian's `unattended-upgrades` (default origins: Debian and Debian-Security). Publishing also commits `Published <title>`.
- **`compose.yml`** runs it. Put `PASSWORD=...` in a `.env` file beside it.

Tests: `python -m venv .venv && .venv/bin/pip install pygame-ce numpy pytest pgzero && .venv/bin/python -m pytest tests`
(tests that use real game files skip unless `ALFIE_GAMES` points at them).
