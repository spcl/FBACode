#!/bin/bash

# find ./build/*/* -maxdepth 0 ! -name '*.log' -exec rm -rf {} \;
find ./build/* -mindepth 1 ! -name '*.log' -exec rm -rf {} \;
rm -rf ./source/*
rm -rf ./compiler_output/*
rm -rf ./ast_archive/*
