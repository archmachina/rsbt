"""PythonSession: builds and publishes a Python package to PyPI via a dedicated venv."""

import os

import rsbt


class PythonSession:
    """Builds and publishes a Python package to PyPI via a dedicated venv."""

    def __init__(self):
        self.venv = "venv"
        self.dist = "dist"
        self.requirements = "requirements.txt"

    def setup(self):
        """Create the venv and install build tooling, plus self.requirements if present."""
        rsbt.bash(
            f"python3 -m venv {self.venv} && "
            f"source {self.venv}/bin/activate && "
            "python3 -m pip install --upgrade pip && "
            "python3 -m pip install --upgrade setuptools build twine"
        )

        if os.path.isfile(self.requirements):
            rsbt.bash(
                f"source {self.venv}/bin/activate && "
                f"python3 -m pip install -r {self.requirements}"
            )

    def build(self):
        """Build the sdist/wheel into self.dist."""
        rsbt.bash(f"source {self.venv}/bin/activate && " "python3 -m build")

    def clean_venv(self):
        """Remove the venv directory."""
        rsbt.bash(f"rm -rf {self.venv}")

    def clean_dist(self):
        """Remove the dist directory."""
        rsbt.bash(f"rm -rf {self.dist}")

    def publish(self, username, password):
        """Upload everything in self.dist to PyPI via twine."""
        rsbt.bash(
            "source ./venv/bin/activate && " f"python3 -m twine upload {self.dist}/*",
            env={"TWINE_USERNAME": username, "TWINE_PASSWORD": password},
        )
