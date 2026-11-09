from pathlib import Path
import tempfile
import shutil

from app import App, ROOT


def app_and_snapshot():
    temp = tempfile.TemporaryDirectory()
    app = App(ROOT / "data", Path(temp.name) / "runtime", Path(temp.name) / "policies")
    isolated_db = Path(temp.name) / "hdt.sqlite"
    shutil.copy2(ROOT / "runtime" / "hdt.sqlite", isolated_db)
    app.twin.t.path = isolated_db
    as_of = app.twin.default_as_of
    return temp, app, as_of, app.twin.snapshot(as_of)
