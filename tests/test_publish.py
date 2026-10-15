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


def test_index_lists_games_sorted_and_escapes_titles():
    page = publish.make_index([("zed", "Zed"), ("pac", 'Pac <b>"Man"</b>')])
    assert page.index('href="pac/"') < page.index('href="zed/"')
    assert "<b>" not in page and "&lt;b&gt;" in page
    assert "Alfie's Arcade" in page


def test_empty_index_has_a_friendly_message():
    assert "No games yet" in publish.make_index([])


def test_write_index_reads_arcade_json(tmp_path):
    (tmp_path / "pacman").mkdir()
    (tmp_path / "pacman" / "arcade.json").write_text(json.dumps({"title": "Pac Alfie"}))
    (tmp_path / "junk").mkdir()  # no arcade.json: not a published game
    publish.write_index(tmp_path)
    page = (tmp_path / "index.html").read_text()
    assert "Pac Alfie" in page and "junk" not in page


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
    assert sorted(p.name for p in published.iterdir()) == ["g", "index.html"]  # no staging leftovers
