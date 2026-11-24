# rsbt

Really Simple Build Tool - a small Python library of helpers for writing
CI/CD build, test, lint, release and deploy pipelines as plain Python
scripts.


## What it provides

- `action` / `run_action()` - register functions as named CLI actions and
  dispatch to them from `sys.argv`, so an `_entrypoint.py` can expose
  `build`, `test`, `lint`, `release`, etc. as subcommands.
- `exec_cmd` / `bash` / `pwsh` / `shell` - run subprocesses with consistent
  logging, exit-code handling and output capture.
- `PythonSession` - build and publish a Python package to PyPI.
- `ContainerSession` - build, tag, log in to a registry and push a
  container image.
- `TestingSession` / `LintingSession` - run a list of shell commands and
  fail the build if any of them fail.
- `BuildSession` - parse a semver version out of one or more candidate
  sources (a git tag, a `GITHUB_REF`, a fallback string).
- `DeploySession` - model an environment promotion chain (e.g.
  `dev -> test -> prod`) and open the promotion pull request on GitHub or
  Forgejo/Gitea.
- `Util` - assorted helpers: git metadata, GitHub releases, and an HTTP
  request helper with built-in retry/backoff for transient failures.

See [`src/rsbt/__init__.py`](src/rsbt/__init__.py) for the full API, this
repo's own [`_entrypoint.py`](_entrypoint.py) for a worked example of
building/testing/releasing a PyPI package with it, and
[`examples/`](examples/) for fuller, reference-only examples of the other
session types (container images, environment promotion).

## Examples

A consuming repo's `_entrypoint.py` registers its pipeline steps as
actions and ends with `rsbt.run_action()`, which dispatches
`./entrypoint <action>` to the matching function.

### A simple Python build

```python
import os

import rsbt
from rsbt import action, Util

bs = rsbt.BuildSession([f"0.1.0-rolling+{Util.git_sha()}"])
pys = rsbt.PythonSession()


@action
def build():
    os.environ["BUILD_VERSION"] = bs.v_mmp
    pys.setup()
    pys.build()


@action
def release():
    bs.update_version([os.environ["GITHUB_REF"]])
    build()
    pys.publish("__token__", os.environ["PYPI_TOKEN"])


rsbt.run_action()
```

### A simple Docker build

```python
import os

import rsbt
from rsbt import action

cs = rsbt.ContainerSession("myorg/myimage", "src/Dockerfile", "src")


@action
def build():
    cs.tags = ["latest"]
    cs.build()


@action
def push():
    build()
    cs.login(
        os.environ["REGISTRY_URL"],
        os.environ["REGISTRY_USERNAME"],
        os.environ["REGISTRY_PASSWORD"],
    )
    cs.push()


rsbt.run_action()
```

### A simple deployment

```python
import os

import rsbt
from rsbt import action

ds = rsbt.DeploySession()
ds.define_env("dev", next_env="prod")
ds.define_env("prod")


@action
def apply():
    env_name = os.environ["DEPLOY_ENV"]
    rsbt.bash(f"ansible-playbook -i inventory/{env_name} site.yml")


@action
def promote():
    ds.promote_github(
        os.environ["DEPLOY_ENV"],
        repo=os.environ["GITHUB_REPOSITORY"],
        promote_token=os.environ["PROMOTE_TOKEN"],
    )


rsbt.run_action()
```

## Self-hosting

`rsbt` builds, tests and releases itself using itself: `requirements.txt`
installs this checkout in editable mode (`-e .`), so `_entrypoint.py`'s
`import rsbt` always resolves to the current working tree rather than a
previously published release. This keeps the self-hosted pipeline honest -
it always exercises the code that is actually being shipped.

## Installing

```
pip install rsbt
```

## Development

`./entrypoint build|test|lint|release` runs the build, test, lint and
release actions defined in `_entrypoint.py`. `test` builds and runs
`src/Dockerfile`'s `testing` stage in a container, so the test suite runs
in a disposable, reproducible environment rather than directly on the
host.
