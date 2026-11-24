import os

from setuptools import find_packages, setup

with open("README.md") as readme_file:
    README = readme_file.read()

setup_args = {
    "name": "rsbt",
    "version": os.environ["BUILD_VERSION"],
    "description": "Really Simple Build Tool - a small library of CI/CD build, test and release helpers",
    "long_description_content_type": "text/markdown",
    "long_description": README,
    "packages": find_packages(where="src", include=["rsbt", "rsbt.*"]),
    "package_dir": {"": "src"},
    "install_requires": [
        "requests>=2.32.3",
    ],
}

if __name__ == "__main__":
    setup(**setup_args, include_package_data=True)
