"""FastAPI application entrypoint tests."""
import runpy
import sys
from types import SimpleNamespace


def test_direct_main_start_disables_uvicorn_reload(monkeypatch):
    """Running main.py directly should not enable WatchFiles reload."""
    calls = []

    fake_uvicorn = SimpleNamespace(
        run=lambda *args, **kwargs: calls.append((args, kwargs))
    )
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    runpy.run_path("main.py", run_name="__main__")

    assert calls
    args, kwargs = calls[0]
    assert args == ("main:app",)
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8000
    assert kwargs["reload"] is False
