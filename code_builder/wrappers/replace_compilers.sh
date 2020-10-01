#!/bin/bash

echo "Replace gcc, g++ & cpp by clang"

for VERSION in "$@"; do
    # rm /usr/bin/g++-$VERSION /usr/bin/gcc-$VERSION /usr/bin/cpp-$VERSION
    ln -fs ${PWD}/clang++ /usr/bin/g++-$VERSION
    ln -fs ${PWD}/clang /usr/bin/gcc-$VERSION
    ln -fs ${PWD}/clang++ /usr/bin/cpp-$VERSION
    ln -fs ${PWD}/clang /usr/bin/cc-$VERSION

    echo "Block the installation of new gcc version $VERSION"
    echo "gcc-$VERSION hold"|dpkg --set-selections
    echo "g++-$VERSION hold"|dpkg --set-selections
done

