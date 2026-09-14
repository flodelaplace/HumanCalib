# Contributing to HumanCalib

HumanCalib exists to make published calibrations reproducible by other labs.
Most rules below protect that property; each one says why.

## Setting up

Pick one:

- **Docker** — `docker compose build`, then `docker compose run --rm calib demo`.
  Nothing else to install besides the NVIDIA container runtime.
- **conda** — `conda env create -f envs/calib.yaml`, `conda activate humancalib`,
  `pip install --no-deps -e .`. `--no-deps` keeps the exact pins of the
  environment instead of letting pip re-resolve them.
- **CPU only, for the tests** — `conda env create -f envs/ci.yaml`. It is the main
  environment without CUDA and TensorFlow, which no test imports.

## Running the tests

```bash
pytest
```

The suite runs on a CPU, without a GPU, a model download or a network, in a few
seconds. CI runs the same suite on every push.

`tests/test_golden_run.py` replays the calibration on frozen poses
(`tests/fixtures/demo_20f`) and compares the camera poses with
`tests/fixtures/golden_expected.json`. Those reference values are not ground
truth: they are what the code produced when it was last validated end to end. If
the test fails, the numbers moved. That is either a bug, or an intended change
you must explain in the commit message. **Never regenerate the reference values
just to make the test pass.**

## Conventions

- **English** for code, comments, messages and figure labels.
- **Logging, not `print`.** Use `log = get_logger(__name__)` from
  `humancalib.core.log`. INFO reaches stdout undecorated, so the output looks the
  same; WARNING and ERROR go to stderr. Do not put `ERROR:` or `WARNING:` inside the
  message — the handler adds the level.
- **No `sys.path` manipulation.** The code is a package under `src/`; import it as
  `humancalib.…`.
- **Steps return their results.** A pipeline step exposes `main(argv=None)` that
  returns what callers need (an MRE, a count). Nothing should parse another step's
  printed output.
- **Command-line compatibility.** `humancalib run` accepts the arguments of
  `scripts/calibrate.sh`, and `tests/test_cli.py` parses the commands of
  `HOWTO.md` verbatim. Changing an option means updating both.
- **Dependencies are declared twice, on purpose.** `pyproject.toml` holds
  compatible ranges; `envs/*.yaml` hold the exact versions that were validated.
  Change them together — `tests/test_env_consistency.py` fails if an exact pin
  falls outside its range.
- **Exceptions.** Catch the narrowest type that can occur, and never swallow one
  without logging why.

## Licensing of contributions

HumanCalib's code is MIT. The pretrained pose models it uses are not: both the
MeTRAbs weights and the VideoPose3D weights are restricted to non-commercial use
by the licences of their training data. Do not bundle model weights or datasets
into the repository, and state the licence of any new model or dataset
dependency in the README.

## Commit messages

Say why, not only what. For a fix, describe the failure it caused — what a user
would have seen, or worse, not seen.
