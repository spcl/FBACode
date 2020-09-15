#!/bin/bash

find ./build/*/* -maxdepth 0 ! -name '*.log' -exec rm -rf {} \;
rm -rf ./source/*
