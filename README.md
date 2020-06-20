*Fetch, Build and Analyze Code*

The project consists of two major components: [*fetcher*](#fetcher) and [*builder*](#builder).
The former is responsible for discovering repositories and source codes. The latter
downloades the code, attempts build and generates LLVM bitcodes.

## Requirements

* Docker: make sure that Docker daemon is running and your user has sufficient permissions to use containers.
* Python (3.6+) with virtual environments and pip. The following Python packages are installed through venv and used:
  - [requests](https://pypi.org/project/requests/)
  - [GitPython](https://pypi.org/project/GitPython/)
  - [docker](https://pypi.org/project/docker/)

## Installation

Run the **install.py** script to create a Python virtual environment **fbacode-virtualenv**
and install dependencies there. Use `source fbacode-virtualenv/bin/activate` to active
the environment.

Use **tools/build_docker_images.py** to build and update Docker images necessary
to run build steps.

## Fetcher

Fetcher attempts to discover available repositories that could be built. The goal
is to search known and popular platforms with open-source code. The output is a JSON
file with entries for each project. The current implementation supports [*GitHub*](#github)
and [*Debian*](#debian) packages.

#### GitHub

The implementation scans GH repositories tagged as C and C++ software and sorts
them according to the number of stars.

To avoid running into [rate limit issues](https://developer.github.com/v3/search/), please provide your [personal access token](https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/) in the user configuration file.

#### Debian

TODO: getting the list of Debian source packages

## Builder

The builder component is responsible for downloading source code, discovering
the build system used for this projects, lookup of existing build instructions
and dependencies and attempting a build. For the build, we use LLVM's Clang and
generate LLVM IR bitcodes.

The Python implementation uses a thread pool to start multiple build processes
at the same time. Each build is invoked in a Docker container for security
and compatibility reasons.

Current implementation supports two build systems: [*CMake*](#cmake) projects
and [*Debian*](#builder-debian) source packages.

Try builder with `builder.py examples/github-repo.json`.

#### CMake

Current implementation supports default configuration without any configuration flags.

#### Debian Builder

TODO

#### Missing features

- Currently we don't perform any search for cloned repositories. Furthermore, it's possible that different platforms provide various versions of the same software, e.g. a GitHub project of a program delivered as a Debian package as well.
- We need a fleet of Docker containers supporting different versions of LLVM.
- We currently don't support discovering and installing dependencies.
- We should use CI configurations (Travis, CircleCI, GH Actions) and package mangers to discover configuration flags and dependencies.
