"""board.py — surface-проводка: ризонинг строит canon-объект, СКРИПТ рендерит под surface.
Гоняем CLI через subprocess (board = тонкая точка входа), проверяем render-session (stdin) и
recipes --surface. Деталь рендереров — в test_session_render/test_recipes; тут — что CLI их зовёт."""
import os, sys, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "..", "scripts", "board.py")

_S = {"question": "q", "synthesis": "s",
      "advisors": [{"name": "Аврелий", "opinions": [{"marker": "blue", "argument": "a"}]}]}


def _run(args, stdin=None):
    return subprocess.run([sys.executable, BOARD, *args], input=stdin,
                          capture_output=True, text=True)


def test_render_session_md_from_stdin():
    r = _run(["render-session", "-", "--surface", "md"], stdin=json.dumps(_S))
    assert r.returncode == 0 and "Аврелий" in r.stdout and "🔵" in r.stdout


def test_render_session_widget_is_clickable():
    r = _run(["render-session", "-", "--surface", "widget"], stdin=json.dumps(_S))
    assert r.returncode == 0 and "sendPrompt(" in r.stdout


def test_render_session_unknown_surface_errors():
    r = _run(["render-session", "-", "--surface", "хм"], stdin=json.dumps(_S))
    assert r.returncode == 2


def test_recipes_widget_surface():
    r = _run(["recipes", "--surface", "widget"])
    assert r.returncode == 0 and "sendPrompt(" in r.stdout


def test_recipes_default_is_text():
    r = _run(["recipes"])
    assert r.returncode == 0 and "<button" not in r.stdout    # текст, не HTML
