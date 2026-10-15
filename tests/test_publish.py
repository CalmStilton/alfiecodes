import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import publish  # noqa: E402


def test_title_comes_from_game_or_falls_back(tmp_path):
    game = tmp_path / "game.py"
    game.write_text('import pgzrun\nTITLE = "Pac <Alfie>"\n')
    assert publish.find_title(game, "pacman") == "Pac <Alfie>"
    game.write_text("WIDTH = 10\n")
    assert publish.find_title(game, "pacman") == "pacman"
    assert publish.find_title(tmp_path / "missing.py", "x") == "x"


def test_index_is_newest_first_and_escapes_titles():
    page = publish.make_index([
        {"folder": "old", "title": "Old one", "published": "2026-01-02"},
        {"folder": "pac", "title": 'Pac <b>"Man"</b>', "published": "2026-10-15", "thumb": "thumb.png"},
    ])
    assert page.index('href="pac/"') < page.index('href="old/"')
    assert "<b>" not in page and "&lt;b&gt;" in page
    assert 'src="pac/thumb.png"' in page
    assert "Published 15 October 2026" in page
    assert '<span class="screen blank" aria-hidden="true">O</span>' in page   # no thumbnail: initial
    assert "<h1>Alfie</h1>" in page


def test_empty_index_has_a_friendly_message():
    page = publish.make_index([])
    assert "Nothing here yet" in page and "<ul" not in page


def test_write_index_reads_project_json(tmp_path):
    (tmp_path / "pacman").mkdir()
    (tmp_path / "pacman" / "project.json").write_text(json.dumps({"title": "Pac Alfie", "published": "2026-10-15"}))
    (tmp_path / "junk").mkdir()  # no project.json: not a published project
    publish.write_index(tmp_path)
    page = (tmp_path / "index.html").read_text()
    assert "Pac Alfie" in page and "Published 15 October 2026" in page and "junk" not in page


def test_snapshot_saves_what_the_game_drew(tmp_path):
    (tmp_path / "game.py").write_text("import pgzrun\nWIDTH = 64\nHEIGHT = 48\ndef draw():\n    screen.fill('hotpink')\npgzrun.go()\n")
    out = tmp_path / "thumb.png"
    assert publish.take_snapshot(tmp_path, out)
    import pygame
    img = pygame.image.load(str(out))
    assert img.get_size() == (64, 48) and tuple(img.get_at((10, 10)))[:3] == (255, 105, 180)


def test_snapshot_of_a_broken_game_fails_quietly(tmp_path):
    (tmp_path / "game.py").write_text("WIDTH = 10\nHEIGHT = 10\ndef draw():\n    oops\n")
    assert publish.take_snapshot(tmp_path, tmp_path / "thumb.png") is False
    (tmp_path / "game.py").write_text("while True:\n    pass\n")
    assert publish.take_snapshot(tmp_path, tmp_path / "thumb.png", timeout=2) is False


@pytest.mark.parametrize("name", ["../etc", "my game", "", "-x", "a/b"])
def test_bad_names_are_refused_before_anything_is_built(name, tmp_path):
    with pytest.raises(publish.PublishError):
        publish.build_web(name, tmp_path, tmp_path)


def test_missing_game_py_is_explained(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(publish.PublishError, match="game.py"):
        publish.build_web("empty", tmp_path, tmp_path / "out")


def test_failed_build_publishes_nothing(tmp_path):
    projects, published = tmp_path / "p", tmp_path / "pub"
    (projects / "g").mkdir(parents=True)
    (projects / "g" / "game.py").write_text("WIDTH = 10\n")
    with pytest.raises(publish.PublishError):
        publish.publish("g", projects, published, pygbag=("false",))
    assert not (published / "g").exists() and not (published / "index.html").exists()


def test_publish_replaces_an_existing_game_and_updates_index(tmp_path):
    projects, published = tmp_path / "p", tmp_path / "pub"
    (projects / "g").mkdir(parents=True)
    (projects / "g" / "game.py").write_text('TITLE = "First"\n')
    fake = tmp_path / "fakepygbag.py"
    fake.write_text(
        "import sys, pathlib\n"
        "app = pathlib.Path(sys.argv[-1]); web = app / 'build' / 'web'; web.mkdir(parents=True)\n"
        "(web / 'index.html').write_text('built ' + (app / 'game.py').read_text())\n"
        "assert (app / 'main.py').exists() and (app / 'pgzlite.py').exists()\n"
    )
    cmd = (sys.executable, str(fake))
    assert publish.publish("g", projects, published, cmd) == "First"
    (projects / "g" / "game.py").write_text('TITLE = "Second"\n')
    assert publish.publish("g", projects, published, cmd) == "Second"
    assert "Second" in (published / "g" / "index.html").read_text()
    assert "Second" in (published / "index.html").read_text() and "First" not in (published / "index.html").read_text()
    meta = json.loads((published / "g" / "project.json").read_text())
    assert meta["published"] and meta["thumb"] == "thumb.png" and (published / "g" / "thumb.png").exists()
    assert sorted(p.name for p in published.iterdir()) == ["g", "index.html"]  # no staging leftovers


def test_cli_usage_names_the_new_command(capsys):
    assert publish.main(["publish"]) == 2
    assert "publish [--run]" in capsys.readouterr().out
