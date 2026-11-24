# Examples

Reference `_entrypoint.py` scripts showing how a consuming repo might use
`rsbt`. These are for reading, not running: they live outside `src/`, so
`setup.py`'s `find_packages(where="src", ...)` never ships them in the
`rsbt` package, and nothing in this repo's own `_entrypoint.py`, lint or
test actions touches this directory.

This repo's own root [`_entrypoint.py`](../_entrypoint.py) is itself a
real, working example of `PythonSession`, `BuildSession`,
`TestingSession` and `LintingSession` - the pipeline that builds, tests
and releases `rsbt` to PyPI. The two examples here cover the session
types that pipeline doesn't use:

- [`container_image/`](container_image/_entrypoint.py) - `ContainerSession`:
  build, tag and push a container image, with a rolling `push_main` and a
  tagged `release`.
- [`environment_promotion/`](environment_promotion/_entrypoint.py) -
  `DeploySession`: model a `dev -> test -> prod` chain and open the pull
  request that promotes one environment to the next.
