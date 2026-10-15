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


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def _repo_with_remote(tmp_path):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.name", "Alfie")
    _git(work, "config", "user.email", "alfie@example.com")
    _git(work, "remote", "add", "origin", str(remote))
    (work / "a").mkdir()
    (work / "a" / "game.py").write_text("x = 1\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "first")
    _git(work, "push", "-q", "-u", "origin", "main")
    return remote, work


def test_publish_commit_holds_only_that_project_and_is_pushed(tmp_path):
    remote, work = _repo_with_remote(tmp_path)
    (work / "a" / "game.py").write_text("x = 2\n")
    (work / "b").mkdir()
    (work / "b" / "game.py").write_text("half finished\n")
    assert publish.record_in_git(work, "a", "Game A")
    assert _git(work, "log", "-1", "--format=%s").strip() == "Published Game A"
    assert _git(work, "show", "--name-only", "--format=", "HEAD").split() == ["a/game.py"]
    assert "b/" in _git(work, "status", "--short")                      # other work left alone
    assert _git(remote, "log", "-1", "--format=%s", "main").strip() == "Published Game A"


def test_publishing_unchanged_code_still_marks_the_moment(tmp_path):
    _, work = _repo_with_remote(tmp_path)
    assert publish.record_in_git(work, "a", "Game A")
    assert _git(work, "log", "-1", "--format=%s").strip() == "Published Game A"


def test_no_git_repo_means_no_git(tmp_path):
    (tmp_path / "a").mkdir()
    assert publish.record_in_git(tmp_path, "a", "Game A") is False


def test_autosave_commits_everything_and_pushes(tmp_path):
    import os, subprocess
    remote, work = _repo_with_remote(tmp_path)
    (work / "b").mkdir()
    (work / "b" / "game.py").write_text("new\n")
    out = subprocess.run([str(ROOT / "autosave.sh")], env=dict(os.environ, PROJECTS=str(work)),
                         capture_output=True, text=True).stdout
    assert "autosave: pushed" in out
    assert _git(remote, "log", "-1", "--format=%s", "main").startswith("Autosave ")
    assert _git(work, "status", "--short") == ""
    out = subprocess.run([str(ROOT / "autosave.sh")], env=dict(os.environ, PROJECTS=str(work)),
                         capture_output=True, text=True).stdout
    assert _git(work, "log", "-1", "--format=%s").startswith("Autosave ") and "pushed" in out   # nothing new: no extra commit
    assert len(_git(work, "log", "--format=%h").split()) == 2


def _workspace(tmp_path):
    projects, published = tmp_path / "w", tmp_path / "pub"
    (projects / "pac-alfie").mkdir(parents=True)
    (projects / "pac-alfie" / "game.py").write_text('# My Pac-Man game\nimport pgzrun\nTITLE = "Pac Alfie"\n')
    (projects / "website").mkdir()
    (projects / "website" / "README.md").write_text("# My first web page\n\nMore words.\n")
    (projects / "scratch").mkdir()
    (projects / "scratch" / "game.py").write_text("#!/usr/bin/env python3\nprint('hi')\n")
    (projects / "empty").mkdir()
    (projects / ".vscode").mkdir()
    (projects / ".vscode" / "tasks.json").write_text("{}")
    (published / "pac-alfie").mkdir(parents=True)
    (published / "pac-alfie" / "project.json").write_text("{}")
    return projects, published


def test_readme_table_lists_every_project_with_descriptions_and_play_links(tmp_path):
    projects, published = _workspace(tmp_path)
    table = publish.project_table(projects, published)
    lines = table.splitlines()
    assert lines[2] == "| [Pac Alfie](pac-alfie/) | My Pac-Man game | [Play](https://alfie.lukmor.com/pac-alfie/) |"
    assert "| [scratch](scratch/) |  |  |" in lines          # shebang isn't a description; not published
    assert "| [website](website/) | My first web page |  |" in lines
    assert "empty" not in table and ".vscode" not in table


def test_readme_update_keeps_alfies_words_and_is_idempotent(tmp_path):
    projects, published = _workspace(tmp_path)
    readme = projects / "README.md"
    readme.write_text("# Alfie's projects\n\nMy words.\n\n<!-- projects:start -->\nold table\n<!-- projects:end -->\n\nMore of my words.\n")
    assert publish.update_readme(projects, published) is True
    text = readme.read_text()
    assert text.startswith("# Alfie's projects\n\nMy words.\n\n<!-- projects:start -->")
    assert text.endswith("<!-- projects:end -->\n\nMore of my words.\n")
    assert "old table" not in text and "Pac Alfie" in text
    assert publish.update_readme(projects, published) is False      # nothing changed the second time


def test_readme_without_markers_gets_the_table_appended(tmp_path):
    projects, published = _workspace(tmp_path)
    (projects / "README.md").write_text("# Hi\n")
    publish.update_readme(projects, published)
    text = (projects / "README.md").read_text()
    assert text.startswith("# Hi\n\n<!-- projects:start -->") and "Pac Alfie" in text


def test_pipes_in_titles_dont_break_the_table(tmp_path):
    projects, published = tmp_path / "w", tmp_path / "pub"
    (projects / "x").mkdir(parents=True)
    (projects / "x" / "game.py").write_text('# A | B\nTITLE = "Left | Right"\n')
    published.mkdir()
    assert "| [Left \\| Right](x/) | A \\| B |  |" in publish.project_table(projects, published)


def test_publish_commit_includes_the_readme(tmp_path):
    remote, work = _repo_with_remote(tmp_path)
    (work / "README.md").write_text("# Mine\n")
    _git(work, "add", "README.md"); _git(work, "commit", "-q", "-m", "readme")
    (work / "README.md").write_text("# Mine\n\nnew table\n")
    (work / "a" / "game.py").write_text("x = 3\n")
    publish.record_in_git(work, "a", "Game A")
    assert sorted(_git(work, "show", "--name-only", "--format=", "HEAD").split()) == ["README.md", "a/game.py"]
