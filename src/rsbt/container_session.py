"""ContainerSession: builds, tags, logs in to a registry for, and pushes a container image."""

import rsbt

from .exceptions import val_arg


class ContainerSession:
    """Builds, tags, logs in to a registry for, and pushes a container image."""

    def __init__(self, container_image, docker_file, container_dir):
        val_arg(isinstance(container_image, str), "Invalid container_image argument. Must be str")
        val_arg(container_image != "", "Empty container_image argument")
        val_arg(isinstance(docker_file, str), "Invalid docker_file argument. Must be str")
        val_arg(docker_file != "", "Empty docker_file argument")
        val_arg(isinstance(container_dir, str), "Invalid container_dir argument. Must be str")
        val_arg(container_dir != "", "Empty container_dir argument")

        self.engine = "docker"
        self.docker_file = docker_file
        self.container_dir = container_dir
        self.container_image = container_image
        self.build_args = []
        self.tags = []
        self.other_build_args = ""

    def build(self):
        """Build the image, tagged with every entry in self.tags."""
        cmd = [f"{self.engine} build -f {self.docker_file} {self.container_dir}"]
        cmd = cmd + [f"--build-arg {x}" for x in self.build_args]
        cmd = cmd + [f"--tag {self.container_image}:{x}" for x in self.tags]
        cmd = cmd + [self.other_build_args]

        rsbt.bash(" ".join(cmd))

    def login(self, registry, username, password):
        """Log the container engine in to registry with username/password."""
        rsbt.bash(
            f"{self.engine} login --password-stdin"
            f' -u "{username}"'
            f' "{registry}" <'
            ' <(echo "$REGISTRY_PASSWORD")',
            env={"REGISTRY_PASSWORD": password},
        )

    def push(self):
        """Push every tag in self.tags to the registry."""
        for tag in self.tags:
            rsbt.bash(f"{self.engine} push {self.container_image}:{tag}")
