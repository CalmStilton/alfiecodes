#!/usr/bin/env python3
"""publish-game <name>: build a game from projects/<name>/game.py for the browser
and add it to the arcade (published/<name>/ plus published/index.html).
publish-game --play <name>: build it and serve it for test-play, publishing nothing.

Environment: PROJECTS (default /config/workspace), PUBLISHED (default /published).
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# pygbag decides what to download by scanning main.py's imports, so pygame must be named here.
MAIN_PY = '''import asyncio
import pygame  # noqa: F401
import pgzlite

asyncio.run(pgzlite.run_file("game.py"))
'''
SKIP = shutil.ignore_patterns("__pycache__", ".git", "build", "*.apk", "main.py", "pgzlite.py")


class PublishError(Exception):
    """A problem Alfie can understand and fix."""


def find_title(game_py, fallback):
    match = re.search(r"""^TITLE\s*=\s*(["'])(.*?)\1""", game_py.read_text(errors="replace"), re.M) if game_py.exists() else None
    return match.group(2) if match and match.group(2).strip() else fallback


def make_index(entries):
    """entries: list of (folder, title). Returns the arcade home page as HTML."""
    cards = "\n".join(
        f'    <a class="game" href="{html.escape(folder, quote=True)}/"><span>{html.escape(title)}</span></a>'
        for folder, title in sorted(entries, key=lambda e: e[1].lower())
    ) or '    <p class="empty">No games yet. Publish one from the editor!</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alfie's Arcade</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;background:#12082b;color:#fff;font:600 1.1rem/1.4 ui-rounded,"Trebuchet MS",system-ui,sans-serif}}
main{{max-width:60rem;margin:0 auto;padding:clamp(1.5rem,5vw,4rem) 1.25rem}}
h1{{font-size:clamp(2rem,7vw,3.6rem);margin:0 0 .25rem;color:#ffd23f;text-shadow:0 .08em 0 #ff3d81}}
p.sub{{margin:0 0 2.5rem;color:#b9a8ff}}
.games{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fill,minmax(13rem,1fr))}}
.game{{display:flex;align-items:center;justify-content:center;min-height:7rem;padding:1rem;text-align:center;text-decoration:none;color:#fff;background:#2b1565;border:3px solid #7c4dff;border-radius:1rem;font-size:1.3rem}}
.game:hover,.game:focus-visible{{background:#ff3d81;border-color:#ffd23f;outline:none}}
.empty{{color:#b9a8ff}}
</style>
</head>
<body>
<main>
  <h1>Alfie's Arcade</h1>
  <p class="sub">Pick a game and press play.</p>
  <div class="games">
{cards}
  </div>
</main>
</body>
</html>
"""


def write_index(published):
    entries = []
    for meta in sorted(published.glob("*/arcade.json")):
        title = json.loads(meta.read_text()).get("title") or meta.parent.name
        entries.append((meta.parent.name, title))
    (published / "index.html").write_text(make_index(entries))


def build_web(name, projects, tmp, pygbag=(sys.executable, "-m", "pygbag")):
    """Build projects/<name> into tmp and return (web_folder, title)."""
    if not NAME_OK.match(name):
        raise PublishError(f"'{name}' can't be a web address. Use letters, numbers, - or _ (no spaces).")
    project = projects / name
    if not (project / "game.py").exists():
        raise PublishError(f"I can't find {project / 'game.py'}. Each game lives in its own folder with a file called game.py.")
    app = Path(tmp) / name  # pygbag names the game after this folder
    shutil.copytree(project, app, ignore=SKIP)
    shutil.copy(HERE / "pgzlite.py", app / "pgzlite.py")
    (app / "main.py").write_text(MAIN_PY)
    result = subprocess.run([*pygbag, "--build", str(app)], capture_output=True, text=True)
    web = app / "build" / "web"
    if result.returncode != 0 or not (web / "index.html").exists():
        sys.stderr.write(result.stdout[-2000:] + result.stderr[-2000:])
        raise PublishError("The build didn't work. The messages above say why.")
    return web, find_title(project / "game.py", name)


def publish(name, projects, published, pygbag=(sys.executable, "-m", "pygbag")):
    with tempfile.TemporaryDirectory(prefix="publish-") as tmp:
        web, title = build_web(name, projects, tmp, pygbag)
        published.mkdir(parents=True, exist_ok=True)
        staging = published / f".{name}.new"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(web, staging)
        (staging / "arcade.json").write_text(json.dumps({"title": title}))
        target = published / name
        old = published / f".{name}.old"
        shutil.rmtree(old, ignore_errors=True)
        if target.exists():
            target.rename(old)
        staging.rename(target)
        shutil.rmtree(old, ignore_errors=True)
    write_index(published)
    return title


def play(name, projects, port=8000):
    """Build and serve a game for test-play. Nothing is published.

    Served on its own port, not through code-server's /proxy/, because that path
    needs the IDE login cookie and pygbag fetches the game file without one.
    """
    with tempfile.TemporaryDirectory(prefix="play-") as tmp:
        web, title = build_web(name, projects, tmp)
        url = os.environ.get("PLAY_URL", f"http://localhost:{port}/")
        print(f"\n'{title}' is ready to play. Open this address:\n\n  {url}\n")
        print("(The first load is slow. Click the page to start. Press Ctrl+C here when you are done.)")
        try:
            subprocess.run([sys.executable, "-m", "http.server", str(port), "--bind", "0.0.0.0", "--directory", str(web)],
                           stderr=subprocess.DEVNULL)
        except KeyboardInterrupt:
            pass


def main(argv):
    args = argv[1:]
    preview = args[:1] == ["--play"]
    if preview:
        args = args[1:]
    if len(args) != 1:
        print("Usage: publish-game [--play] <game-folder-name>")
        return 2
    projects = Path(os.environ.get("PROJECTS", "/config/workspace"))
    published = Path(os.environ.get("PUBLISHED", "/published"))
    try:
        if preview:
            play(args[0], projects)
            return 0
        title = publish(args[0], projects, published)
    except PublishError as err:
        print(f"\nCouldn't build it: {err}")
        return 1
    print(f"\nPublished '{title}'. It is on the arcade page now.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
