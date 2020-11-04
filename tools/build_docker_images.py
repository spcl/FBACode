#!/usr/bin/env python3

import docker
import os
import json
import sys

PROJECT_DIR = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), os.path.pardir)
DOCKER_DIR = os.path.join(PROJECT_DIR, 'docker')
REPOSITORY_NAME = 'mcopik/fbacode'

images = {
    'ubuntu-1804-clang-9': {
        'dockerfile': 'ubuntu-1804-clang-9.dockerfile'
    },
    # 'debian-sid': {
    #     'dockerfile': 'Dockerfile_debian-sid.base'
    # },
    'debian-buster': {
        'dockerfile': 'Dockerfile_debian-buster.base'
    },
    # 'debian-bullseye': {
    #     'dockerfile': 'Dockerfile_debian-bullseye.base'
    # }
    'ubuntu-2004-travis': {
        'dockerfile': 'ubuntu-2004-travis.dockerfile'
    }
}

no_cache = False
if len(sys.argv) > 1 and sys.argv[1] == "--nocache":
    no_cache = True


client = docker.from_env()
errors = 0
for i, (img, definitions) in enumerate(images.items()):
    print("[{}/{}] building {}:{}".format(i +
                                          1, len(images), REPOSITORY_NAME, img))
    dockerfile = definitions['dockerfile']
    cli = docker.APIClient()
    response = cli.build(
        path=PROJECT_DIR,
        dockerfile=os.path.join(DOCKER_DIR, dockerfile),
        rm=True,
        nocache=no_cache,
        tag="{}:{}".format(REPOSITORY_NAME, img)
    )
    for i in response:
        resp = json.loads(i.decode())
        if "stream" in resp:
            print(resp["stream"], end='')
        elif "error" in resp:
            print("ERROR: {}".format(resp["error"]), end='')
            print(resp["errorDetail"], end='')
            errors += 1
print("\n {} errors in {} docker builds".format(errors, len(images)))
sys.exit(bool(errors))
