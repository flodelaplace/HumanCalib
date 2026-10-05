"""Download the MeTRAbs model once, visibly and resumably, into the TensorFlow-Hub cache.

tensorflow_hub.load(url) downloads the ~708 MB archive itself, but shows no progress, never
times out and cannot resume: on a slow or flaky connection the first run sat on "Loading
MeTRAbs model -- please wait..." for hours with nothing to tell a stall from progress. Here the
archive is fetched with a progress bar, resumed after an interruption (HTTP Range) and retried,
then unpacked where TF-Hub itself would put it -- a directory named after the SHA-1 of the URL
under TFHUB_CACHE_DIR -- so a model cached by an earlier version, or by TF-Hub, is reused as is.
"""
import hashlib
import os
import shutil
import tarfile
import time
import urllib.error
import urllib.request

from humancalib.core.log import get_logger

log = get_logger(__name__)

CHUNK = 1 << 20
RETRIES = 8
TIMEOUT_S = 60


def cache_dir():
    return os.path.normpath(os.environ.get("TFHUB_CACHE_DIR") or os.path.join(
        os.path.expanduser("~"), ".cache", "tfhub_modules"))


def module_dir(url, root=None):
    """Where TF-Hub caches `url`: <root>/<sha1(url)>."""
    return os.path.join(root or cache_dir(), hashlib.sha1(url.encode("utf8")).hexdigest())


def is_saved_model(path):
    return os.path.isfile(os.path.join(path, "saved_model.pb"))


def _download(url, dest, what="MeTRAbs model", offline=None):
    """Fetch `url` into `dest`, resuming a partial file and retrying on network errors."""
    from tqdm import tqdm

    part = dest + ".part"
    total = None
    for attempt in range(1, RETRIES + 1):
        done = os.path.getsize(part) if os.path.isfile(part) else 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={done}-"} if done else {})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                if done and resp.status != 206:       # the server ignored the range: start over
                    done = 0
                length = resp.headers.get("Content-Length")
                total = done + int(length) if length else total
                with open(part, "ab" if done else "wb") as f, tqdm(
                        total=total, initial=done, unit="B", unit_scale=True, unit_divisor=1024,
                        desc=f"  Downloading {what}") as bar:
                    while True:
                        block = resp.read(CHUNK)
                        if not block:
                            break
                        f.write(block)
                        bar.update(len(block))
            if total is None or os.path.getsize(part) >= total:
                os.replace(part, dest)
                return
            raise urllib.error.URLError("connection closed before the end of the file")
        except (urllib.error.URLError, OSError, TimeoutError) as err:
            if attempt == RETRIES:
                raise RuntimeError(
                    f"could not download the {what} from {url} after {RETRIES} attempts "
                    f"({err}). The partial file is kept in {part} and the next run resumes it. "
                    "Behind a proxy, set HTTPS_PROXY; offline, place "
                    f"{offline or 'the unpacked model in ' + dest[:-len('.tar.gz')]}.") from err
            wait = min(60, 5 * attempt)
            log.warning(f"download interrupted ({err}); resuming in {wait} s "
                        f"(attempt {attempt + 1}/{RETRIES})")
            time.sleep(wait)


def _remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.lexists(path):
        os.remove(path)


def ensure_model(url):
    """Local directory of the SavedModel for `url`, downloading and unpacking it if needed."""
    target = module_dir(url)
    if is_saved_model(target):
        return os.path.realpath(target)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    archive = target + ".tar.gz"
    if not os.path.isfile(archive):
        log.info(f"  -> First run: downloading the MeTRAbs model (~700 MB, once) to {target}")
        _download(url, archive)
    log.info("  -> Unpacking the model...")
    tmp = target + ".unpacking"
    _remove(tmp)
    with tarfile.open(archive) as tar:
        try:
            tar.extractall(tmp, filter="data")      # refuses unsafe paths (Python >= 3.10.12)
        except TypeError:
            tar.extractall(tmp)
    found = tmp if is_saved_model(tmp) else next(
        (os.path.join(tmp, d) for d in os.listdir(tmp) if is_saved_model(os.path.join(tmp, d))), None)
    if found is None:
        _remove(tmp)
        os.remove(archive)
        raise RuntimeError(f"the archive from {url} holds no saved_model.pb; deleted, retry the run")
    _remove(target)                                 # an empty or broken directory left by TF-Hub
    os.replace(found, target)
    _remove(tmp)
    with open(target + ".descriptor.txt", "w") as f:
        f.write(f"Module: {url}\nDownloaded by HumanCalib\n")
    os.remove(archive)
    return os.path.realpath(target)


def ensure_file(url, filename, sha256, what="model", root=None):
    """Local path of a single model file, downloaded once into ~/.cache/humancalib and checked.

    HUMANCALIB_MODEL_DIR overrides the folder, e.g. to use a copy on a machine without internet.
    """
    root = os.path.normpath(root or os.environ.get("HUMANCALIB_MODEL_DIR") or os.path.join(
        os.path.expanduser("~"), ".cache", "humancalib"))
    path = os.path.join(root, filename)
    if os.path.isfile(path) and _sha256(path) == sha256:
        return path
    os.makedirs(root, exist_ok=True)
    log.info(f"  -> First run: downloading the {what} (once) to {path}")
    _download(url, path, what=what, offline=f"{filename} in {root} (or set HUMANCALIB_MODEL_DIR)")
    if _sha256(path) != sha256:
        os.remove(path)
        raise RuntimeError(f"the {what} downloaded from {url} is corrupted (checksum mismatch); "
                           "deleted, retry the run")
    return path


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()
