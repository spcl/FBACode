#!/usr/bin/env python3

import docker
import os
import json
import sys
import configparser

PROJECT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir)
DOCKER_DIR = os.path.join(PROJECT_DIR, "docker")
REPOSITORY_NAME = "mcopik/fbacode"

images = {
    "ubuntu-2004-clang": {"dockerfile": "ubuntu-2004-clang.dockerfile"},
    # 'debian-sid': {
    #     'dockerfile': 'Dockerfile_debian-sid.base'
    # },
    "debian-buster-clang": {"dockerfile": "debian-buster-clang.dockerfile"},
    # 'debian-bullseye': {
    #     'dockerfile': 'Dockerfile_debian-bullseye.base'
    # }
    "ubuntu-bionic-clang": {"dockerfile": "ubuntu-bionic-clang.dockerfile"},
    # 'ubuntu-trusty-clang': {
    #     'dockerfile': 'ubuntu-trusty-clang.dockerfile'
    # },
    "ubuntu-xenial-clang": {"dockerfile": "ubuntu-xenial-clang.dockerfile"},
    "ubuntu-focal-clang": {"dockerfile": "ubuntu-focal-clang.dockerfile"},
}

# default version 9, lets try to read version from config file
clang_version = "9"
config = configparser.ConfigParser()
config_path = os.path.dirname(__file__) + "/../build.cfg"
try:
    config.read(config_path)
    if "build" in config and "clang_version" in config["build"]:
        clang_version = str(config["build"]["clang_version"])
except Exception as e:
    print(
        "error {} opening config file {}, defaulting to clang version {}".format(
            e, config_path, clang_version
        )
    )


no_cache = False
verbose = False
if len(sys.argv) > 1 and "--nocache" in sys.argv:
    no_cache = True
if len(sys.argv) > 1 and "-v" in sys.argv:
    verbose = True

client = docker.from_env()  # type: ignore
errors = 0
for i, (img, definitions) in enumerate(images.items()):
    print(
        "\n\n[{}/{}] building {}:{}-{}".format(
            i + 1, len(images), REPOSITORY_NAME, img, clang_version
        )
    )
    dockerfile = definitions["dockerfile"]
    cli = docker.APIClient()  # type: ignore
    print("initialized APICLINET")
    response = cli.build(
        path=PROJECT_DIR,
        dockerfile=os.path.join(DOCKER_DIR, dockerfile),
        rm=True,
        nocache=no_cache,
        tag="{}:{}-{}".format(REPOSITORY_NAME, img, clang_version),
        buildargs={"CLANG_VERSION": clang_version},
    )
    for i in response:
        resp = json.loads(i.decode())
        if verbose and "stream" in resp:
            print("  " + resp["stream"], end="")
        elif "error" in resp:
            if "stream" in resp:
                print("  " + resp["stream"], end="")
            print("  " + "ERROR: {}".format(resp["error"]), end="")
            print("  " + str(resp["errorDetail"]), end="")
            errors += 1
print("\n {} errors in {} docker builds".format(errors, len(images)))
sys.exit(bool(errors))
