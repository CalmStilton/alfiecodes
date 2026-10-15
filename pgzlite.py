"""pgzlite: a small Pygame Zero look-alike that runs in the browser under pygbag.

Pygame Zero's pgzrun.go() blocks, which pygbag (WebAssembly) can't do. pgzlite
supplies the Pygame Zero names a beginner's game uses and drives the game's
update() and draw() from an async loop. A game file written for pgzrun runs
unchanged: the pgzrun import and pgzrun.go() lines are removed when it loads.

Supported: WIDTH/HEIGHT/TITLE, update()/update(dt), draw(), on_key_down,
on_mouse_down, screen.fill/clear, screen.draw.(filled_)circle/(filled_)rect/
line/text, keyboard.<name>, Rect, named and RGB colours, 60 fps.
Not yet: Actor, images, sounds, clock, music.
Text uses pygame's default font at the same size Pygame Zero asks for.
"""
import asyncio
import inspect
import os
import re
import textwrap
import traceback

import pygame
from pygame import Rect

FPS = 60

# Lines that only make sense under pgzrun. Blanked, not deleted, so error
# messages keep the line numbers Alfie sees in his editor.
_PGZRUN_LINE = re.compile(r"^[ \t]*(import pgzrun|from pgzrun import \*|pgzrun\.go\(\))[ \t]*(#.*)?$", re.M)

_ANCHORS = {"topleft", "topright", "bottomleft", "bottomright",
            "midtop", "midleft", "midbottom", "midright", "center"}


def _color(c):
    if isinstance(c, pygame.Color):
        return c
    if isinstance(c, str):
        return pygame.Color(c)
    return pygame.Color(*c)


class _Draw:
    def __init__(self, screen):
        self._screen = screen

    @property
    def _surf(self):
        return self._screen.surface

    def filled_circle(self, pos, radius, color):
        pygame.draw.circle(self._surf, _color(color), pos, radius)

    def circle(self, pos, radius, color):
        pygame.draw.circle(self._surf, _color(color), pos, radius, 1)

    def filled_rect(self, rect, color):
        pygame.draw.rect(self._surf, _color(color), rect)

    def rect(self, rect, color):
        pygame.draw.rect(self._surf, _color(color), rect, 1)

    def line(self, start, end, color):
        pygame.draw.line(self._surf, _color(color), start, end)

    def text(self, text, pos=None, *, fontsize=24, color="white", **options):
        """Draw text at pos (top-left) or anchored with topright=, center=, etc.

        Other Pygame Zero options (shadow, outline, background...) are ignored.
        """
        font = pygame.font.Font(None, fontsize)
        image = font.render(str(text), True, _color(color))
        rect = image.get_rect()
        if pos is not None:
            rect.topleft = pos
        for name, value in options.items():
            if name in _ANCHORS:
                setattr(rect, name, value)
        self._surf.blit(image, rect)


class _Screen:
    surface = None

    def __init__(self):
        self.draw = _Draw(self)

    @property
    def width(self):
        return self.surface.get_width()

    @property
    def height(self):
        return self.surface.get_height()

    def fill(self, color):
        self.surface.fill(_color(color))

    def clear(self):
        self.surface.fill((0, 0, 0))


class _Keyboard:
    _forced = None  # tests set this to a set of held key names

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        name = name.lower()
        try:
            code = pygame.key.key_code(name)
        except ValueError:
            raise AttributeError(f"There is no key called {name!r}") from None
        if self._forced is not None:
            return name in self._forced
        return bool(pygame.key.get_pressed()[code])


screen = _Screen()
keyboard = _Keyboard()


def namespace():
    """The names a game file expects to find without importing them."""
    return {"__name__": "__main__", "screen": screen, "keyboard": keyboard, "Rect": Rect}


def strip_pgzrun(source):
    return _PGZRUN_LINE.sub("", source)


def load_source(source, filename="game.py"):
    """Run a game's source and return its namespace (hooks, WIDTH, globals)."""
    ns = namespace()
    exec(compile(strip_pgzrun(source), filename, "exec"), ns)
    return ns


def _call(fn, *args):
    """Call a hook with as many of args as it accepts, as Pygame Zero does."""
    params = inspect.signature(fn).parameters.values()
    if any(p.kind == p.VAR_POSITIONAL for p in params):
        return fn(*args)
    return fn(*args[:len([p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])])


def _error_lines(exc, filename):
    line = getattr(exc, "lineno", None) if isinstance(exc, SyntaxError) else None
    if line is None:
        for frame in reversed(traceback.extract_tb(exc.__traceback__)):
            if frame.filename == filename:
                line = frame.lineno
                break
    where = f"in {filename}, line {line}" if line else f"in {filename}"
    return ["Oops! Python found a problem", f"{type(exc).__name__}: {exc}", where]


def _draw_error(surface, lines):
    surface.fill((90, 0, 0))
    font = pygame.font.Font(None, 30)
    chars = max(20, surface.get_width() // 12)
    y = 20
    for line in lines:
        for part in textwrap.wrap(line, chars) or [""]:
            surface.blit(font.render(part, True, (255, 255, 255)), (20, y))
            y += 34
        y += 10


async def run(ns, *, max_frames=None, on_frame=None, error=None, filename="game.py", catch=True):
    """Drive a loaded game. max_frames/on_frame are for tests; error shows a load failure."""
    pygame.init()
    pygame.font.init()
    size = (ns.get("WIDTH", 800), ns.get("HEIGHT", 600)) if error is None else (640, 480)
    screen.surface = pygame.display.set_mode(size)
    pygame.display.set_caption(ns.get("TITLE", "Pygame Zero Game") if error is None else "Oops")
    clock = pygame.time.Clock()
    failed = error
    if failed is not None:
        _draw_error(screen.surface, _error_lines(failed, filename))
    frame = 0
    while max_frames is None or frame < max_frames:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if failed is None and event.type == pygame.KEYDOWN and "on_key_down" in ns:
                _call(ns["on_key_down"], event.key, event.mod, event.unicode)
            if failed is None and event.type == pygame.MOUSEBUTTONDOWN and "on_mouse_down" in ns:
                _call(ns["on_mouse_down"], event.pos, event.button)
        dt = clock.tick(FPS) / 1000
        if failed is None:
            try:
                if "update" in ns:
                    _call(ns["update"], dt)
                if "draw" in ns:
                    ns["draw"]()
            except Exception as exc:
                if not catch:
                    raise
                traceback.print_exc()
                failed = exc
                _draw_error(screen.surface, _error_lines(exc, filename))
        pygame.display.flip()
        frame += 1
        if on_frame:
            on_frame(frame)
        await asyncio.sleep(0)


async def run_file(path="game.py"):
    """Entry point for the generated main.py."""
    filename = os.path.basename(path)
    with open(path) as f:
        source = f.read()
    try:
        ns = load_source(source, filename)
    except Exception as exc:
        traceback.print_exc()
        await run({}, error=exc, filename=filename)
        return
    await run(ns, filename=filename)
