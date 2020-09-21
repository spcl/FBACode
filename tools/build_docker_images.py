#!/usr/bin/env python3

import docker
import os
import json

PROJECT_DIR = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), os.path.pardir)
DOCKER_DIR = os.path.join(PROJECT_DIR, 'docker')
REPOSITORY_NAME = 'mcopik/fbacode'

images = {
    # 'ubuntu-1804-clang-9': {
    #     'dockerfile': 'Dockerfile.base'
    # },
    # 'debian-sid': {
    #     'dockerfile': 'Dockerfile_debian-sid.base'
    # },
    'debian-buster': {
        'dockerfile': 'Dockerfile_debian-buster.base'
    },
    # 'debian-bullseye': {
    #     'dockerfile': 'Dockerfile_debian-bullseye.base'
    # }
}

client = docker.from_env()

for i, (img, definitions) in enumerate(images.items()):
    print("[{}/{}] building {}:{}".format(i +
                                          1, len(images), REPOSITORY_NAME, img))
    dockerfile = definitions['dockerfile']
    # image, log = client.images.build(
    #     path=PROJECT_DIR,
    #     dockerfile=os.path.join(DOCKER_DIR, dockerfile),
    #     tag="{}:{}".format(REPOSITORY_NAME, img)
    # )
    # for i in log:
    #     print(i)
    cli = docker.APIClient()
    response = cli.build(
        path=PROJECT_DIR,
        dockerfile=os.path.join(DOCKER_DIR, dockerfile),
        rm=False,
        tag="{}:{}".format(REPOSITORY_NAME, img)
    )
    for i in response:
        resp = json.loads(i.decode())
        if "stream" in resp:
            print(resp["stream"], end='')
        elif "error" in resp:
            print("ERROR: {}".format(resp["error"]), end='')
            print(resp["errorDetail"], end='')

