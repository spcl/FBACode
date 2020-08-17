#!/bin/bash

echo "Replace gcc, g++ & cpp by clang"
for VERSION in "$@"; do
    rm /usr/bin/g++-$VERSION /usr/bin/gcc-$VERSION /usr/bin/cpp-$VERSION
    ln -s clang++ /usr/bin/g++-$VERSION
    ln -s clang /usr/bin/gcc-$VERSION
    ln -s clang++ /usr/bin/cpp-$VERSION
    ln -s clang /usr/bin/cc-$VERSION

    echo "Block the installation of new gcc version $VERSION"
    echo "gcc-$VERSION hold"|dpkg --set-selections
    echo "cpp-$VERSION hold"|dpkg --set-selections
    echo "g++-$VERSION hold"|dpkg --set-selections
    echo "cc-$VERSION hold"|dpkg --set-selections
done

echo "Check if gcc, g++ & cpp are actually clang"
gcc --version|grep clang > /dev/null || exit 1
