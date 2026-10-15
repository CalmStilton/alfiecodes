#!/usr/bin/env python3
"""publish <name>: build projects/<name>/game.py for the browser and add it to
Alfie's projects page (published/<name>/ plus published/index.html).
publish --run <name>: build it and serve it for a try-out, publishing nothing.

Environment: PROJECTS (default /config/workspace), PUBLISHED (default /published).
"""
import datetime
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


def _published_on(iso):
    try:
        d = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"Published {d.day} {d:%B %Y}"


def make_index(entries):
    """entries: dicts with folder, title, and optionally published (ISO date) and thumb.
    Returns the public projects page as HTML, newest first."""
    tiles = []
    for e in sorted(entries, key=lambda e: (e.get("published") or "", e["title"].lower()), reverse=True):
        folder = html.escape(e["folder"], quote=True)
        title = html.escape(e["title"])
        if e.get("thumb"):
            screen = (f'<span class="screen"><img src="{folder}/{html.escape(e["thumb"], quote=True)}" '
                      f'alt="Screenshot of {html.escape(e["title"], quote=True)}" loading="lazy"></span>')
        else:
            screen = f'<span class="screen blank" aria-hidden="true">{html.escape(e["title"][:1].upper())}</span>'
        date = _published_on(e.get("published"))
        tiles.append(
            f'    <li><a class="tile" href="{folder}/">{screen}'
            f'<span class="name">{title}</span>'
            + (f'<span class="date">{date}</span>' if date else "")
            + "</a></li>"
        )
    body = (
        '  <p class="hint">Games take a few seconds to load. Click the game to start it.</p>\n'
        '  <ul class="tiles">\n' + "\n".join(tiles) + "\n  </ul>"
    ) if tiles else '  <p class="empty">Nothing here yet. Check back soon.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Alfie</title>
<style>
:root{{--bg:#F5F7FA;--ink:#1B2230;--muted:#5E6878;--line:#DCE1E8;--accent:#2440FF;--screen:#0E1220}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12161F;--ink:#E8ECF2;--muted:#98A2B3;--line:#2A3140;--accent:#7C8CFF;--screen:#080B12}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:400 1rem/1.5 "Avenir Next",Avenir,"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
main{{max-width:72rem;margin:0 auto;padding:clamp(2.5rem,8vw,6rem) clamp(1.25rem,4vw,2.5rem) 5rem}}
h1{{margin:0;font-family:"Avenir Next","Segoe UI Variable Display","Segoe UI",system-ui,sans-serif;font-weight:800;font-size:clamp(4rem,14vw,9rem);line-height:.88;letter-spacing:-.045em}}
.lede{{margin:1.25rem 0 0;max-width:34rem;font-size:clamp(1.1rem,2.2vw,1.35rem);color:var(--muted)}}
.hint{{margin:clamp(3rem,7vw,5rem) 0 1.5rem;padding-top:1.25rem;border-top:1px solid var(--line);font-size:.9rem;color:var(--muted)}}
.empty{{margin:clamp(3rem,7vw,5rem) 0 0;padding-top:1.25rem;border-top:1px solid var(--line);color:var(--muted)}}
.tiles{{list-style:none;margin:0;padding:0;display:grid;gap:2.5rem 1.75rem;grid-template-columns:repeat(auto-fill,minmax(min(100%,16rem),1fr))}}
.tile{{display:block;color:inherit;text-decoration:none}}
.screen{{position:relative;display:grid;place-items:center;aspect-ratio:4/3;background:var(--screen);border-radius:12px;overflow:hidden;outline:3px solid transparent;outline-offset:4px;transition:outline-color .12s}}
.screen img{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}}
.screen.blank{{color:#3A4256;font-weight:800;font-size:4rem}}
.tile:hover .screen,.tile:focus-visible .screen{{outline-color:var(--accent)}}
.tile:focus-visible{{outline:none}}
.name{{display:block;margin-top:.9rem;font-weight:600;font-size:1.1rem;letter-spacing:-.01em}}
.date{{display:block;margin-top:.15rem;font-size:.875rem;color:var(--muted)}}
@media (prefers-reduced-motion:reduce){{.screen{{transition:none}}}}
</style>
</head>
<body>
<main>
  <h1>Alfie</h1>
  <p class="lede">Games and other things I’ve made with Python.</p>
{body}
</main>
</body>
</html>
"""


def write_index(published):
    entries = []
    for meta in sorted(published.glob("*/project.json")):
        data = json.loads(meta.read_text())
        entries.append({"folder": meta.parent.name, "title": data.get("title") or meta.parent.name,
                        "published": data.get("published"), "thumb": data.get("thumb")})
    (published / "index.html").write_text(make_index(entries))


# Runs a game off-screen for a moment and saves what it drew. A separate process,
# so a game that hangs or crashes can't stop the publish.
SNAPSHOT_PY = """
import asyncio, sys
sys.path.insert(0, sys.argv[1])
import pygame, pgzlite
pgzlite.FPS = 0
pgzlite.keyboard._forced = set()
with open("game.py") as f:
    ns = pgzlite.load_source(f.read(), "game.py")
asyncio.run(pgzlite.run(ns, max_frames=30, catch=False))
pygame.image.save(pgzlite.screen.surface, sys.argv[2])
"""


def take_snapshot(project, out_png, timeout=30):
    """Save a screenshot of the game to out_png. Returns True if it worked."""
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", PYGAME_HIDE_SUPPORT_PROMPT="1")
    try:
        result = subprocess.run([sys.executable, "-c", SNAPSHOT_PY, str(HERE), str(out_png)],
                                cwd=project, env=env, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0 and Path(out_png).exists()


def build_web(name, projects, tmp, pygbag=(sys.executable, "-m", "pygbag")):
    """Build projects/<name> into tmp and return (web_folder, title)."""
    if not NAME_OK.match(name):
        raise PublishError(f"'{name}' can't be a web address. Use letters, numbers, - or _ (no spaces).")
    project = projects / name
    if not (project / "game.py").exists():
        raise PublishError(f"I can't find {project / 'game.py'}. Each project lives in its own folder, and a game needs a file called game.py.")
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
        meta = {"title": title, "published": datetime.date.today().isoformat()}
        if take_snapshot(projects / name, staging / "thumb.png"):
            meta["thumb"] = "thumb.png"
        (staging / "project.json").write_text(json.dumps(meta))
        target = published / name
        old = published / f".{name}.old"
        shutil.rmtree(old, ignore_errors=True)
        if target.exists():
            target.rename(old)
        staging.rename(target)
        shutil.rmtree(old, ignore_errors=True)
    write_index(published)
    return title


def run(name, projects, port=8000):
    """Build and serve a project for a try-out. Nothing is published.

    Served on its own port, not through code-server's /proxy/, because that path
    needs the IDE login cookie and pygbag fetches the game file without one.
    """
    with tempfile.TemporaryDirectory(prefix="run-") as tmp:
        web, title = build_web(name, projects, tmp)
        url = os.environ.get("PREVIEW_URL", f"http://localhost:{port}/")
        print(f"\n'{title}' is running. Open this address:\n\n  {url}\n")
        print("(The first load is slow. Click the page to start. Press Ctrl+C here when you are done.)")
        try:
            subprocess.run([sys.executable, "-m", "http.server", str(port), "--bind", "0.0.0.0", "--directory", str(web)],
                           stderr=subprocess.DEVNULL)
        except KeyboardInterrupt:
            pass


def main(argv):
    args = argv[1:]
    preview = args[:1] == ["--run"]
    if preview:
        args = args[1:]
    if len(args) != 1:
        print("Usage: publish [--run] <project-folder-name>")
        return 2
    projects = Path(os.environ.get("PROJECTS", "/config/workspace"))
    published = Path(os.environ.get("PUBLISHED", "/published"))
    try:
        if preview:
            run(args[0], projects)
            return 0
        title = publish(args[0], projects, published)
    except PublishError as err:
        print(f"\nCouldn't build it: {err}")
        return 1
    print(f"\nPublished '{title}'. It is on your projects page now.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
