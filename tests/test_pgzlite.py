import asyncio
import os
import pathlib
import subprocess
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pgzlite  # noqa: E402

pgzlite.FPS = 0  # no frame limiter in tests

# Real games are not stored in this public repo. Point ALFIE_GAMES elsewhere to test them.
GAMES = pathlib.Path(os.environ.get("ALFIE_GAMES", "/project/src/Thinky-Stack/alfies-arcade"))
needs_games = pytest.mark.skipif(not (GAMES / "PacMan.py").exists(), reason="game files not present")


def play(source, frames, held=(), on_frame=None, catch=False):
    """Load a game from source and run it headless. Returns its namespace."""
    ns = pgzlite.load_source(source)
    pgzlite.keyboard._forced = set(held)
    asyncio.run(pgzlite.run(ns, max_frames=frames, on_frame=on_frame, catch=catch))
    return ns


def px(x, y):
    return tuple(pgzlite.screen.surface.get_at((x, y)))[:3]


SYNTHETIC = """
import pgzrun
TITLE = "Synthetic"
WIDTH = 200
HEIGHT = 100
calls = []
def update(dt):
    calls.append(("update", dt >= 0))
def draw():
    calls.append(("draw",))
    screen.fill("black")
    screen.draw.filled_rect(Rect(10, 10, 30, 30), "blue")
    screen.draw.filled_circle((100, 50), 10, "hotpink")
    screen.draw.filled_rect(Rect(150, 10, 20, 20), (1, 2, 3))
    screen.draw.text("Hi", topright=(190, 5), fontsize=40, color="white")
pgzrun.go()
"""


def test_hooks_run_in_order_and_window_uses_game_settings():
    ns = play(SYNTHETIC, 3)
    assert ns["calls"][:4] == [("update", True), ("draw",), ("update", True), ("draw",)]
    assert pgzlite.screen.surface.get_size() == (200, 100)
    assert pygame.display.get_caption()[0] == "Synthetic"


def test_drawing_primitives_and_colours():
    play(SYNTHETIC, 1)
    assert px(20, 20) == (0, 0, 255)           # named colour "blue"
    assert px(100, 50) == (255, 105, 180)      # "hotpink"
    assert px(160, 20) == (1, 2, 3)            # RGB tuple
    assert px(5, 90) == (0, 0, 0)              # fill
    right = [px(x, y) for x in range(150, 191) for y in range(5, 30)]
    assert any(c == (255, 255, 255) for c in right)  # topright= text landed on the right


def test_update_without_dt_and_hooks_with_fewer_args():
    src = "WIDTH = 50\nHEIGHT = 50\nn = 0\ndef update():\n    global n\n    n += 1\ndef draw():\n    pass\n"
    assert play(src, 5)["n"] == 5


def test_keyboard_held_and_unknown_key():
    src = "WIDTH = 50\nHEIGHT = 50\nx = 0\ndef update():\n    global x\n    if keyboard.left:\n        x -= 1\n    if keyboard.r:\n        x += 10\ndef draw():\n    pass\n"
    assert play(src, 3, held={"left"})["x"] == -3
    assert play(src, 2, held={"r"})["x"] == 20
    with pytest.raises(AttributeError):
        pgzlite.keyboard.notakey


def test_key_and_mouse_events_reach_the_game():
    src = "WIDTH = 50\nHEIGHT = 50\ngot = []\ndef on_key_down(key):\n    got.append(key)\ndef on_mouse_down(pos):\n    got.append(pos)\ndef draw():\n    pass\n"
    pygame.init()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" "))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(3, 4), button=1))
    assert play(src, 1)["got"] == [pygame.K_SPACE, (3, 4)]


def test_pgzrun_lines_removed_but_line_numbers_kept():
    src = "import pgzrun\nx = 1\nfrom pgzrun import *\npgzrun.go()  # go\n"
    out = pgzlite.strip_pgzrun(src)
    assert out.count("\n") == src.count("\n")
    assert "pgzrun" not in out and "x = 1" in out


def test_game_error_shows_a_message_instead_of_vanishing(capsys):
    src = "WIDTH = 300\nHEIGHT = 200\ndef draw():\n    screen.fill('black')\n    oops = missing_name\n"
    play(src, 2, catch=True)
    assert px(299, 199) == (90, 0, 0)  # error screen background
    assert "NameError" in capsys.readouterr().err


def test_syntax_error_at_load_shows_error_screen(tmp_path, capsys):
    game = tmp_path / "game.py"
    game.write_text("WIDTH = 100\nif True:\nx = 1\n")
    exc = None
    try:
        pgzlite.load_source(game.read_text(), "game.py")
    except SyntaxError as e:
        exc = e
    assert exc is not None
    assert pgzlite._error_lines(exc, "game.py")[2] == "in game.py, line 3"
    asyncio.run(pgzlite.run({}, max_frames=1, error=exc))
    assert px(639, 479) == (90, 0, 0)


# ---- Alfie's and Luke's real games (skipped if the files aren't here) -----------------

@needs_games
def test_alfies_pacman_first_frame_and_moves():
    src = (GAMES / "PacMan.py").read_text()
    first = {}

    def grab(frame):
        if frame == 1:
            first["wall"] = px(8, 8)
            first["ghost"] = px(400, 80)
            first["dot"] = px(60, 60)
            first["pac_edge"] = px(240 + 15, 240)

    ns = play(src, 120, held={"right"}, on_frame=grab)
    assert first["wall"] == (0, 0, 255)
    assert first["ghost"] == (255, 0, 0)
    assert first["dot"] == (255, 255, 255)
    assert first["pac_edge"] == (255, 255, 0)
    assert ns["pac_x"] > 240          # moved right
    assert ns["score"] >= 1           # ate at least the dot under the start position
    assert ns["pac_x"] < 464 - 20     # the wall stopped it


def pacdaddy(solid):
    # PacDaddy.py line 14 says `ghost_solid = true`; run it with the obvious fix.
    text = (GAMES / "PacDaddy.py").read_text()
    return text.replace("ghost_solid = true", f"ghost_solid = {solid}")


@needs_games
def test_pacdaddy_solid_ghost_is_stopped_by_walls_and_speed_text_shows():
    seen = {}

    def grab(frame):
        if frame == 1:
            seen["speed"] = any(px(x, y) == (255, 255, 255) for x in range(380, 461) for y in range(20, 45))

    ns = play(pacdaddy(True), 1500, on_frame=grab)
    assert seen["speed"], "Speed: text at topright= should be drawn"
    assert (ns["ghost_x"], ns["ghost_y"]) == (240, 159)   # stuck on the wall above an idle Pac-Man
    assert ns["game_over"] is False


@needs_games
def test_pacdaddy_spooky_ghost_catches_then_r_restarts():
    ns = play(pacdaddy(False), 400)
    assert ns["game_over"] is True
    assert px(240, 240) != (0, 0, 0)                      # GAME OVER text is on screen
    asyncio.run(pgzlite.run(ns, max_frames=1, catch=False))   # frame with no keys: still over
    assert ns["game_over"] is True
    pgzlite.keyboard._forced = {"r"}
    asyncio.run(pgzlite.run(ns, max_frames=1, catch=False))
    assert ns["game_over"] is False and ns["score"] == 0


@needs_games
def test_pacdaddy_win_message_when_all_dots_eaten():
    src = pacdaddy(True) + "\ndots.clear()\n"
    ns = play(src, 2)
    assert any(px(x, 240) == (255, 255, 0) for x in range(100, 380))   # yellow "YOU WIN!"


@needs_games
def test_same_file_still_runs_under_real_pgzrun():
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    pgzrun = pathlib.Path(sys.executable).with_name("pgzrun")
    result = subprocess.run(["timeout", "3", str(pgzrun), str(GAMES / "PacMan.py")],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 124, result.stderr   # 124 = still running when timeout stopped it
