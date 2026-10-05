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

## Model files

The RTMPose backend downloads `videopose3d_h36m_detectron_coco.onnx` (68 MB), attached as an
asset to the GitHub release v0.3.1 (URL and SHA-256 in `src/humancalib/core/models.py`). Assets
are added by *editing* an existing release: that triggers neither a new Zenodo archive nor the
PyPI workflow, which a new release would. To replace the file after a new conversion
(`scripts/export_videopose3d_onnx.py`), attach it under a new name to the current release and
update the file name, URL and checksum together, so that existing installs keep downloading the
file they were checked against.

## Zenodo

The repository is connected to Zenodo: each published GitHub Release is archived and gets its
own DOI. The concept DOI 10.5281/zenodo.23143081 always resolves to the latest version; cite it
in the README and CITATION.cff, and the version DOI in a paper that used that exact version.
