"""The MeTRAbs model download: fresh, resumed after a cut, and reused from the TF-Hub cache."""
import io
import os
import tarfile
import urllib.error

import pytest

from humancalib.pose import model_download as md

URL = "https://example.org/model.tar.gz"


def _archive():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in (("./saved_model.pb", b"graph"), ("./variables/variables.index", b"idx")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _Response(io.BytesIO):
    def __init__(self, data, status):
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def server(monkeypatch, tmp_path):
    """A fake HTTP server honouring Range; `cut_after` bytes of the first reply, then an error."""
    monkeypatch.setenv("TFHUB_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(md.time, "sleep", lambda s: None)
    state = {"data": _archive(), "cut_after": None, "calls": 0}

    def urlopen(req, timeout):
        state["calls"] += 1
        rng = req.headers.get("Range")
        start = int(rng.split("=")[1].rstrip("-")) if rng else 0
        body = state["data"][start:]
        if state["cut_after"] is not None:
            body, state["cut_after"] = body[:state["cut_after"]], None
            resp = _Response(body, 206 if start else 200)
            resp.headers["Content-Length"] = str(len(state["data"]) - start)   # promised more
            return resp
        return _Response(body, 206 if start else 200)

    monkeypatch.setattr(md.urllib.request, "urlopen", urlopen)
    return state


def test_fresh_download_lands_where_tfhub_looks(server):
    path = md.ensure_model(URL)
    assert os.path.isfile(os.path.join(path, "saved_model.pb"))
    assert path == os.path.realpath(md.module_dir(URL))
    assert not os.path.exists(md.module_dir(URL) + ".tar.gz")


def test_interrupted_download_resumes(server):
    server["cut_after"] = 40
    path = md.ensure_model(URL)
    assert os.path.isfile(os.path.join(path, "variables", "variables.index"))
    assert server["calls"] == 2


def test_cached_model_is_reused_without_network(server):
    os.makedirs(md.module_dir(URL))
    open(os.path.join(md.module_dir(URL), "saved_model.pb"), "w").close()
    md.ensure_model(URL)
    assert server["calls"] == 0


def test_persistent_failure_keeps_the_partial_file(server, monkeypatch):
    def down(req, timeout):
        raise urllib.error.URLError("no route")
    monkeypatch.setattr(md.urllib.request, "urlopen", down)
    with pytest.raises(RuntimeError, match="resumes"):
        md.ensure_model(URL)
