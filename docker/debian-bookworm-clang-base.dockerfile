FROM debian:bookworm

ARG CLANG_VERSION
RUN echo "building image for clang version ${CLANG_VERSION}"

# add source code repos to debian
RUN rm -f /etc/apt/sources.list
RUN rm -f /etc/apt/sources.list.d/*
# TODO: do this with sed or something
COPY docker/sources_bookworm.list /etc/apt/sources.list

ARG deps='software-properties-common curl gpg-agent gnupg wget unzip' 
ARG soft="libomp-${CLANG_VERSION}-dev \
libllvm${CLANG_VERSION} llvm-${CLANG_VERSION} llvm-${CLANG_VERSION}-dev \
llvm-${CLANG_VERSION}-runtime clang-${CLANG_VERSION} clang-tools-${CLANG_VERSION} \
libclang-common-${CLANG_VERSION}-dev libclang-${CLANG_VERSION}-dev libclang1-${CLANG_VERSION} \
clangd-${CLANG_VERSION} libc++-${CLANG_VERSION}-dev libc++abi-${CLANG_VERSION}-dev"
RUN apt-get update 
RUN apt-get install -y ${deps} --no-install-recommends
RUN curl https://apt.llvm.org/llvm-snapshot.gpg.key | apt-key add -
# https://apt.llvm.org/
RUN add-apt-repository "deb http://apt.llvm.org/bookworm/ llvm-toolchain-bookworm main"
RUN add-apt-repository "deb http://apt.llvm.org/bookworm/ llvm-toolchain-bookworm-17 main"
RUN add-apt-repository "deb http://apt.llvm.org/bookworm/ llvm-toolchain-bookworm-18 main"

RUN apt-get update
RUN apt-get install -y ${soft} --no-install-recommends
RUN apt-get purge -y --auto-remove ${DEPS}
RUN ln -s /usr/bin/clang-${CLANG_VERSION} /usr/bin/clang
RUN ln -s /usr/bin/clang++-${CLANG_VERSION} /usr/bin/clang++

# install latest version of CMake (hardcoded)
RUN mkdir /tmp/cmake-install && wget -qO- "https://cmake.org/files/v3.28/cmake-3.28.3-linux-x86_64.tar.gz" | tar --strip-components=1 -xz -C /tmp/cmake-install
RUN ln -s /tmp/cmake-install/bin/cmake /usr/bin/cmake
RUN ln -s /tmp/cmake-install/bin/ccmake /usr/bin/ccmake

# install latest version of ninja-build (hardcoded)
RUN wget -O /tmp/ninja-build.zip "https://github.com/ninja-build/ninja/releases/download/v1.11.1/ninja-linux.zip" && unzip /tmp/ninja-build.zip -d /usr/bin