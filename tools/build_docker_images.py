#!/usr/bin/env python3

import argparse
import docker
import json
import os
import shutil

PROJECT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir)
DOCKER_DIR = os.path.join(PROJECT_DIR, 'docker')
REPOSITORY_NAME = 'mcopik/fbacode'

images = {
    'ubuntu-1804-clang-9': {
        'dockerfile': 'Dockerfile.base'
    },
    'debian-buster': {
        'dockerfile': 'Dockerfile_debian.base'
    }
}

client = docker.from_env()

for img, definitions in images.items():
    dockerfile = definitions['dockerfile']
    client.images.build(
        path=PROJECT_DIR,
        dockerfile=os.path.join(DOCKER_DIR,dockerfile),
        tag="{}:{}".format(REPOSITORY_NAME,img)
    )
