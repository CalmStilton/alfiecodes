#!/usr/bin/env python3
"""publish <name>: build projects/<name> for the browser (a Pygame Zero game.py, or a
website with an index.html) and add it to
Alfie's projects page (published/<name>/ plus published/index.html).
publish --run <name>: build it and serve it for a try-out, publishing nothing.
publish --readme: refresh the project table in the workspace README.

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
WEB_SKIP = shutil.ignore_patterns(".*", "__pycache__", "build", "node_modules")


class PublishError(Exception):
    """A problem Alfie can understand and fix."""


def find_title(game_py, fallback):
    match = re.search(r"""^TITLE\s*=\s*(["'])(.*?)\1""", game_py.read_text(errors="replace"), re.M) if game_py.exists() else None
    return match.group(2) if match and match.group(2).strip() else fallback


def project_kind(folder):
    """What sort of project a folder holds, from its files:
    "game" (a Pygame Zero game.py), "website" (index.html), "python" (a game.py
    that isn't a Pygame Zero game, e.g. a print()/input() program), or None."""
    game = folder / "game.py"
    if game.exists():
        src = game.read_text(errors="replace")
        if re.search(r"^\s*def\s+draw\s*\(|\bpgzrun\b|\bscreen\.", src, re.M):
            return "game"
        return "python"
    if (folder / "index.html").exists():
        return "website"
    return None


def project_title(folder):
    """A game's TITLE, a website's <title>, or else the folder name."""
    if (folder / "game.py").exists():
        return find_title(folder / "game.py", folder.name)
    index = folder / "index.html"
    if index.exists():
        match = re.search(r"<title[^>]*>(.*?)</title>", index.read_text(errors="replace"), re.I | re.S)
        if match and match.group(1).strip():
            return html.unescape(" ".join(match.group(1).split()))
    return folder.name


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
  <p class="lede">Games and other things I’ve made.</p>
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


# Restyle pygbag's game page to match the projects page. The canvas itself is
# left alone: pygbag warns that borders or padding on it break mouse positions.
GAME_PAGE_STYLE = """<style id="alfie-style">
body{background:#12161F !important;color:#E8ECF2;font-family:"Avenir Next",Avenir,"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif}
#infobox{background:rgba(232,236,242,.12) !important;color:#E8ECF2 !important;font:600 15px/1.3 "Avenir Next",Avenir,"Segoe UI",system-ui,sans-serif !important;padding:10px 22px !important;border-radius:999px}
#status{color:#98A2B3 !important;font-family:inherit !important;font-weight:600 !important}
#alfie-home{position:fixed;top:14px;left:16px;z-index:1000000;padding:6px 14px;border-radius:999px;background:rgba(232,236,242,.12);color:#E8ECF2;font:800 15px/1.2 "Avenir Next",Avenir,"Segoe UI",system-ui,sans-serif;letter-spacing:-.02em;text-decoration:none}
#alfie-home:hover,#alfie-home:focus-visible{background:#7C8CFF;color:#12161F;outline:none}
</style>
"""
GAME_PAGE_HOME = '<a id="alfie-home" href="../">Alfie</a>\n'


# Touch controls: real HTML buttons beside the game, shown only on touch screens.
# A press sends the same keydown/keyup a keyboard would, to the document, which
# is where pygbag's SDL listens, so keyboard.left etc. just work.
ARROWS = {
    "up": ("ArrowUp", "ArrowUp", 38, "▲"),
    "left": ("ArrowLeft", "ArrowLeft", 37, "◀"),
    "right": ("ArrowRight", "ArrowRight", 39, "▶"),
    "down": ("ArrowDown", "ArrowDown", 40, "▼"),
}
OTHER_KEYS = {
    "space": (" ", "Space", 32, "Space"),
    "return": ("Enter", "Enter", 13, "Enter"),
    "enter": ("Enter", "Enter", 13, "Enter"),
    "escape": ("Escape", "Escape", 27, "Esc"),
    "tab": ("Tab", "Tab", 9, "Tab"),
    "backspace": ("Backspace", "Backspace", 8, "⌫"),
    "lshift": ("Shift", "ShiftLeft", 16, "Shift"),
    "rshift": ("Shift", "ShiftRight", 16, "Shift"),
    "lctrl": ("Control", "ControlLeft", 17, "Ctrl"),
    "rctrl": ("Control", "ControlRight", 17, "Ctrl"),
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    OTHER_KEYS[_c] = (_c, f"Key{_c.upper()}", ord(_c.upper()), _c.upper())
for _d in "0123456789":
    OTHER_KEYS[f"k_{_d}"] = (_d, f"Digit{_d}", ord(_d), _d)


def touch_keys(source):
    """The keys a game reads through keyboard.<name>: (arrow names, other key names), in first-use order."""
    arrows, others = [], []
    for name in re.findall(r"\bkeyboard\.([A-Za-z_][A-Za-z0-9_]*)", source):
        name = name.lower()
        if name in ARROWS and name not in arrows:
            arrows.append(name)
        elif name in OTHER_KEYS and name not in others:
            others.append(name)
    return arrows, others


def _touch_button(name, spec, cls):
    key, code, key_code, label = spec
    return (f'<button type="button" class="{cls}" data-key="{html.escape(key, quote=True)}" data-code="{code}" '
            f'data-keycode="{key_code}" aria-label="{html.escape(name, quote=True)}">{html.escape(label)}</button>')


def touch_controls(arrows, others):
    """HTML, CSS and JS for the on-screen controls. Empty if the game reads no keys."""
    if not arrows and not others:
        return ""
    pad = ""
    if arrows:
        cells = "".join(_touch_button(n, ARROWS[n], f"pad-{n}") for n in ("up", "left", "right", "down") if n in arrows)
        pad = f'<div class="pad">{cells}</div>'
    acts = "".join(_touch_button(n, OTHER_KEYS[n], "act") for n in others)
    acts = f'<div class="acts">{acts}</div>' if acts else ""
    return """<style id="alfie-touch-style">
#alfie-touch{display:none}
@media (pointer:coarse){#alfie-touch{display:flex}}
#alfie-touch{position:fixed;left:0;right:0;bottom:0;z-index:1000000;justify-content:space-between;align-items:flex-end;padding:0 18px max(18px,env(safe-area-inset-bottom));pointer-events:none}
#alfie-touch button{pointer-events:auto;touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none;-webkit-tap-highlight-color:transparent;border:1px solid rgba(232,236,242,.22);background:rgba(232,236,242,.14);color:#E8ECF2;font:700 18px/1 "Avenir Next",Avenir,"Segoe UI",system-ui,sans-serif;margin:0;padding:0}
#alfie-touch button.down-now{background:#7C8CFF;color:#12161F;border-color:#7C8CFF}
#alfie-touch .pad{display:grid;grid-template-columns:repeat(3,64px);grid-template-rows:repeat(3,64px);gap:6px}
#alfie-touch .pad button{border-radius:14px}
#alfie-touch .pad-up{grid-area:1/2}#alfie-touch .pad-left{grid-area:2/1}#alfie-touch .pad-right{grid-area:2/3}#alfie-touch .pad-down{grid-area:3/2}
#alfie-touch .acts{display:flex;gap:12px;margin-left:auto}
#alfie-touch .act{min-width:76px;height:76px;padding:0 16px;border-radius:38px}
</style>
<div id="alfie-touch">""" + pad + acts + """</div>
<script>
(() => {
  const send = (b, type) => {
    const k = +b.dataset.keycode;
    const e = new KeyboardEvent(type, {key: b.dataset.key, code: b.dataset.code, bubbles: true, cancelable: true});
    Object.defineProperty(e, "keyCode", {get: () => k});
    Object.defineProperty(e, "which", {get: () => k});
    document.dispatchEvent(e);
  };
  document.querySelectorAll("#alfie-touch button").forEach(b => {
    const press = ev => { if (b.classList.contains("down-now")) return; b.classList.add("down-now"); try { b.setPointerCapture(ev.pointerId); } catch (x) {} send(b, "keydown"); };
    const release = () => { if (!b.classList.contains("down-now")) return; b.classList.remove("down-now"); send(b, "keyup"); };
    b.addEventListener("pointerdown", press);
    ["pointerup", "pointercancel", "lostpointercapture"].forEach(t => b.addEventListener(t, release));
    b.addEventListener("contextmenu", ev => ev.preventDefault());
  });
})();
</script>
"""


def restyle_game_page(page, title, home_link=True, touch=""):
    """Make pygbag's generated index.html match Alfie's projects page, and add touch controls."""
    text = page.read_text()
    text = text.replace("Ready to start ! Please click/touch page", "Click or tap to start")
    text = text.replace("Loading, please wait ...", "Loading. The first visit takes about 30 seconds.")
    text = re.sub(r"<title>.*?</title>", lambda m: f"<title>{html.escape(title)}</title>", text, count=1)
    extra = GAME_PAGE_STYLE + (GAME_PAGE_HOME if home_link else "") + touch
    text = text.replace("</body>", extra + "</body>", 1) if "</body>" in text else text + extra
    page.write_text(text)


def build_web(name, projects, tmp, pygbag=(sys.executable, "-m", "pygbag"), home_link=True):
    """Build projects/<name> into tmp and return (web_folder, title).

    Games go through pgzlite and pygbag; websites are copied as they are."""
    if not NAME_OK.match(name):
        raise PublishError(f"'{name}' can't be a web address. Use letters, numbers, - or _ (no spaces).")
    project = projects / name
    if not project.is_dir():
        raise PublishError(f"I can't find a project folder called '{name}'.")
    kind = project_kind(project)
    title = project_title(project)
    if kind == "website":
        web = Path(tmp) / name / "web"
        shutil.copytree(project, web, ignore=WEB_SKIP)
        return web, title
    if kind == "python":
        raise PublishError("game.py doesn't look like a Pygame Zero game: it has no draw() and doesn't use screen. "
                           "Programs that use print() and input() can't go on the web yet. Ask Daddy.")
    if kind is None:
        raise PublishError("I don't know how to put this project on the web yet. A game needs a file called game.py, "
                           "and a website needs a file called index.html. For anything else, ask Daddy.")
    app = Path(tmp) / name  # pygbag names the game after this folder
    shutil.copytree(project, app, ignore=SKIP)
    shutil.copy(HERE / "pgzlite.py", app / "pgzlite.py")
    (app / "main.py").write_text(MAIN_PY)
    result = subprocess.run([*pygbag, "--build", str(app)], capture_output=True, text=True)
    web = app / "build" / "web"
    if result.returncode != 0 or not (web / "index.html").exists():
        sys.stderr.write(result.stdout[-2000:] + result.stderr[-2000:])
        raise PublishError("The build didn't work. The messages above say why.")
    source = (project / "game.py").read_text(errors="replace")
    restyle_game_page(web / "index.html", title, home_link, touch_controls(*touch_keys(source)))
    return web, title


README_START = "<!-- projects:start -->"
README_END = "<!-- projects:end -->"
NOT_PROJECTS = {"build", "__pycache__", "node_modules"}


def describe(folder):
    """A project's one-line description: a first-line comment in game.py or main.py,
    a website's <meta name="description">, or the first line of the folder's README.md.
    Empty if there isn't one."""
    for name in ("game.py", "main.py"):
        f = folder / name
        if f.exists():
            first = (f.read_text(errors="replace").splitlines() or [""])[0].strip()
            if first.startswith("#") and not first.startswith("#!") and "coding" not in first:
                return first.lstrip("#").strip()
    index = folder / "index.html"
    if index.exists():
        match = re.search(r"""<meta\s+name=["']description["']\s+content=["']([^"']*)["']""",
                          index.read_text(errors="replace"), re.I)
        if match and match.group(1).strip():
            return html.unescape(match.group(1).strip())
    readme = folder / "README.md"
    if readme.exists():
        for line in readme.read_text(errors="replace").splitlines():
            if line.strip():
                return line.strip().lstrip("#").strip()
    return ""


def project_table(projects):
    """The Markdown table of every project folder, for the workspace README."""
    rows = []
    for folder in sorted(p for p in projects.iterdir()
                         if p.is_dir() and not p.name.startswith(".") and p.name not in NOT_PROJECTS
                         and any(p.iterdir())):
        title = project_title(folder)
        cell = lambda text: text.replace("|", "\\|")
        rows.append((title.lower(), f"| [{cell(title)}]({folder.name}/) | {cell(describe(folder))} |"))
    lines = ["| Project | What it is |", "|---|---|"] + [r for _, r in sorted(rows)]
    return "\n".join(lines)


def update_readme(projects):
    """Rebuild the table between the README markers. Everything else in the README
    is Alfie's and is left exactly as it is. Returns True if the file changed."""
    readme = projects / "README.md"
    if not readme.exists():
        return False
    text = readme.read_text()
    block = (f"{README_START}\n<!-- This table updates itself when you publish and every evening. -->\n"
             f"{project_table(projects)}\n{README_END}")
    if README_START in text and README_END in text:
        before, rest = text.split(README_START, 1)
        after = rest.split(README_END, 1)[1]
        new = before + block + after
    else:
        new = text.rstrip("\n") + "\n\n" + block + "\n"
    if new == text:
        return False
    readme.write_text(new)
    return True


def record_in_git(projects, name, title, timeout=30):
    """Commit "Published <title>" for this project if the workspace is a git repo, then push.

    Only this project's folder and the README go in the commit (empty if unchanged, so the
    history still marks the moment). Never fails the publish: the nightly
    autosave pushes anything that didn't make it.
    """
    if not (projects / ".git").exists():
        return False
    def git(*args):
        try:
            return subprocess.run(["git", "-C", str(projects), *args], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
    paths = [name] + (["README.md"] if (projects / "README.md").exists() else [])
    git("add", "-A", "--", *paths)
    done = git("commit", "-q", "--allow-empty", "--only", "-m", f"Published {title}", "--", *paths)
    git("push", "-q")
    return bool(done and done.returncode == 0)


def publish(name, projects, published, pygbag=(sys.executable, "-m", "pygbag")):
    with tempfile.TemporaryDirectory(prefix="publish-") as tmp:
        web, title = build_web(name, projects, tmp, pygbag)
        published.mkdir(parents=True, exist_ok=True)
        staging = published / f".{name}.new"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(web, staging)
        meta = {"title": title, "published": datetime.date.today().isoformat()}
        if project_kind(projects / name) == "game" and take_snapshot(projects / name, staging / "thumb.png"):
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
        web, title = build_web(name, projects, tmp, home_link=False)
        url = os.environ.get("PREVIEW_URL", f"http://localhost:{port}/")
        print(f"\n'{title}' is running. Open this address:\n\n  {url}\n")
        if project_kind(projects / name) == "game":
            print("(The first load is slow. Click the page to start. Press Ctrl+C here when you are done.)")
        else:
            print("(Press Ctrl+C here when you are done.)")
        try:
            subprocess.run([sys.executable, "-m", "http.server", str(port), "--bind", "0.0.0.0", "--directory", str(web)],
                           stderr=subprocess.DEVNULL)
        except KeyboardInterrupt:
            pass


def main(argv):
    args = argv[1:]
    projects = Path(os.environ.get("PROJECTS", "/config/workspace"))
    published = Path(os.environ.get("PUBLISHED", "/published"))
    if args == ["--readme"]:
        update_readme(projects)
        return 0
    preview = args[:1] == ["--run"]
    if preview:
        args = args[1:]
    if len(args) != 1:
        print("Usage: publish [--run] <project-folder-name>   (or: publish --readme)")
        return 2
    # The editor passes the open file's folder; a file in a subfolder (dog-site/pics)
    # still belongs to the project at the top (dog-site).
    args[0] = args[0].replace("\\", "/").strip("/").split("/")[0]
    try:
        if preview:
            run(args[0], projects)
            return 0
        title = publish(args[0], projects, published)
        update_readme(projects)
        record_in_git(projects, args[0], title)
    except PublishError as err:
        print(f"\nCouldn't build it: {err}")
        return 1
    print(f"\nPublished '{title}'. It is on your projects page now.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
