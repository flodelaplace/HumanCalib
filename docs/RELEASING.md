# Releasing

Releases are built and uploaded by GitHub Actions (`.github/workflows/publish.yml`) with
PyPI Trusted Publishing: no password or token is stored anywhere.

## One-time setup (about 5 minutes)

1. Create an account on [pypi.org](https://pypi.org/account/register/) (and, to rehearse,
   on [test.pypi.org](https://test.pypi.org/account/register/)), with two-factor
   authentication.
2. On pypi.org: *Your account → Publishing → Add a new pending publisher*, GitHub tab:

   | Field | Value |
   |---|---|
   | PyPI project name | `humancalib` |
   | Owner | `flodelaplace` |
   | Repository name | `HumanCalib` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

   Same on test.pypi.org, with environment name `testpypi`.
3. Optional but recommended: on GitHub, *Settings → Environments*, create `pypi` and
   require your own approval, so that nothing is uploaded without a click.

The project name is reserved by the first upload; until then the pending publisher holds it.

## Rehearse on TestPyPI

GitHub → *Actions → publish → Run workflow*. It builds, checks and uploads to TestPyPI. Then,
in a fresh environment:

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ \
    "humancalib[gpu]"
humancalib --version
```

A version can be uploaded only once to each index; to rehearse again, bump the version.

## Release

1. Update the version in `pyproject.toml` and `CITATION.cff` (`version`, `date-released`),
   and move the changes under a new heading in `CHANGELOG.md`.
2. Run the tests, commit on `main`, tag and push:

   ```bash
   git tag -a v0.3.1 -m "HumanCalib 0.3.1"
   git push origin main v0.3.1
   ```

3. GitHub → *Releases → Draft a new release*, choose the tag, paste the changelog section,
   *Publish release*. The workflow checks that the tag matches the package version, builds,
   installs the wheel on its own, and uploads to PyPI.

## After the first upload to PyPI

The installation instructions in `README.md` point at the GitHub archive of a tag, which
works without PyPI. Once the package is on PyPI, replace them with the shorter form:

```bash
pip install "humancalib[gpu]"
```

(the `@ https://github.com/.../vX.Y.Z.zip` part goes away, in the pip, Windows and CPU-only
instructions).
