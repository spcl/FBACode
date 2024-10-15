ARG CLANG_VERSION
# TODO: remove test
FROM spcleth/fbacode:debian-bookworm-clang-base-test-${CLANG_VERSION}

ARG CLANG_VERSION
RUN echo "building image for clang version ${CLANG_VERSION}"

# do not run tests on builds (does not work for all pkgs)
# also, do not try to optimize debug symbols (dwz executable returns error code if it cannot find .debugsymbols)
ENV DEB_BUILD_OPTIONS="nocheck nostrip"
ENV CLANG_VERSION=${CLANG_VERSION}

ARG deps='software-properties-common curl gpg-agent gnupg wget unzip' 
ARG soft="python3 make texinfo build-essential fakeroot devscripts dh-make git procps config-package-dev apt-utils git"

RUN apt-get update 
RUN apt-get install -y ${deps} --no-install-recommends
RUN apt-get install -y ${soft} --no-install-recommends

RUN mkdir -p /opt/source/
RUN git clone https://github.com/ConstantinDragancea/ClangToolExtractSourceFiles.git /opt/source/ClangToolExtractSourceFiles
ENV EXTRACT_SOURCE_FILES_PROJECT_ROOT=/opt/source/ClangToolExtractSourceFiles
RUN mkdir -p ${EXTRACT_SOURCE_FILES_PROJECT_ROOT}/build && cd ${EXTRACT_SOURCE_FILES_PROJECT_ROOT}/build && rm -rf ./* && cmake -G "Ninja" -DCMAKE_CXX_COMPILER=clang++-${CLANG_VERSION} -DCMAKE_MAKE_PROGRAM=ninja -DCMAKE_C_COMPILER=clang-${CLANG_VERSION} -DCLANG_DIR=/usr/lib/llvm-${CLANG_VERSION}/lib/cmake/clang ../ && ninja
