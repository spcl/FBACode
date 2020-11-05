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
and [*Debian*](#debian) packages. To enable or disable sources, use the `fetch.cfg` 
file and set the `active` field accordingly 

#### GitHub

The implementation scans GH repositories tagged as C and C++ software and sorts
them according to the number of stars.

To avoid running into [rate limit issues](https://developer.github.com/v3/search/), please provide your [personal access token](https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/) in the user configuration file.

#### Debian

The fetcher looks for random projects with C or C++ code in them, which is found in the debian package API.
At the moment only Debian 10 (Buster) is supported. 


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

Try builder with `builder.py examples/github-repo.json` or `builder.py examples/debian.json`.

The builder outputs several files to the `buildlogs` folder:
- `summary-XXX.txt`: basically the same output as the console, shows errors and other build statiscics
- `build_details_XXX.json`: contains all the information gathered for each project
- `errorstats_XXX.json`: A sorted list of all errors found, with packages and numbers of occurences
- `rebuild_XXX.json`: A json file with all the failed projects, can be fed to the Builder again
- `dependencies_XXX.json`: A sorted list of all missing dependencies found

#### CMake

Current implementation supports default configuration without any configuration flags.

#### Make

Current implementation basically runs `./configure` and then `make`.

#### Autotools

Current implementation basically runs `autoreconf`,  `./configure` and then `make`. Does not work correctly yet.

#### Travis CI

The builder tries to pick a configuration with `os: linux`, `compiler: clang` and `arch: amd64`
otherwise just picks the first configuration from the build matrix. The apt and snap addons are
supported, as well as stages. 

#### Debian Builder

The current implementation uses packages from the Debian 10 (Buster, latest LTS at the time) repository.
The Packages get downloaded inside the docker container, since we don't know if apt is
available on the host system. it basically runs `apt-source package`, then 
`apt build-dep package` to install dependencies and finally `dpkg-buildpackage` to build it.
because the configure and build step is combined into one command, it is not possible to 
time them separately.

#### Missing features

- Currently we don't perform any search for cloned repositories. Furthermore, it's possible that different platforms provide various versions of the same software, e.g. a GitHub project of a program delivered as a Debian package as well.
- We need a fleet of Docker containers supporting different versions of LLVM.
- installing dependencies is missing
- discovering dependencies is not very good yet
- We should use CI configurations (Travis, CircleCI, GH Actions) and package mangers to discover configuration flags and dependencies.
