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
ARG soft="python3 make texinfo build-essential fakeroot devscripts dh-make git procps config-package-dev apt-utils"

RUN apt-get update 
RUN apt-get install -y ${deps} --no-install-recommends
RUN apt-get install -y ${soft} --no-install-recommends
RUN apt-get purge -y --auto-remove ${deps}


ENV HOME_DIR /home/fba_code/
ENV SRC_DIR ${HOME_DIR}/code
ENV BUILD_DIR ${HOME_DIR}/build
ENV BITCODES_DIR ${HOME_DIR}/bitcodes

# install cxx-langstat from einstein local source code
RUN mkdir -p /opt/source/
ADD cxx-langstat /opt/source/cxx-langstat
ENV CXX_LANGSTAT_PROJECT_PATH=/opt/source/cxx-langstat
RUN mkdir -p ${CXX_LANGSTAT_PROJECT_PATH}/build && cd ${CXX_LANGSTAT_PROJECT_PATH}/build && rm -rf ./* && cmake -G "Ninja" -DCMAKE_CXX_COMPILER=clang++-${CLANG_VERSION} -DCMAKE_MAKE_PROGRAM=ninja -DCMAKE_C_COMPILER=clang-${CLANG_VERSION} -DCLANG_DIR=/usr/lib/llvm-${CLANG_VERSION}/lib/cmake/clang ../ && ninja

RUN cp ${CXX_LANGSTAT_PROJECT_PATH}/build/cxx-langstat /usr/lib/llvm-${CLANG_VERSION}/bin
RUN ln -fs /usr/lib/llvm-${CLANG_VERSION}/bin/cxx-langstat /usr/bin/cxx-langstat
RUN mkdir -p ${HOME_DIR}/analyze

# set the environment variables for c/cxx
# ENV CC ${HOME_DIR}/wrappers/clang
# ENV CXX ${HOME_DIR}/wrappers/clang++

# fixes for qmake
# https://salsa.debian.org/lucas/collab-qa-tools/-/blob/master/modes/clang10
# Force the configruation of qmake to workaround this issue:
# https://clang.debian.net/status.php?version=9.0.1&key=FAILED_PARSE_DEFAULT

RUN apt install --yes --no-install-recommends qt5-qmake
RUN cp /usr/lib/x86_64-linux-gnu/qt5/mkspecs/linux-clang/* /usr/lib/x86_64-linux-gnu/qt5/mkspecs/linux-g++/
RUN ls -al /usr/lib/x86_64-linux-gnu/qt5/mkspecs/linux-g++/
RUN cat /usr/lib/x86_64-linux-gnu/qt5/mkspecs/linux-g++/qmake.conf
ENV QMAKESPEC=/usr/lib/x86_64-linux-gnu/qt5/mkspecs/linux-clang/

RUN sed -i -e "s|compare_problem(2,|compare_problem(0,|g" /usr/bin/dpkg-gensymbols
RUN sed -i -e "s|compare_problem(1,|compare_problem(0,|g" /usr/bin/dpkg-gensymbols
RUN grep "compare_problem(" /usr/bin/dpkg-gensymbols

RUN apt search '^gcc-[0-9]*[.]*[0-9]*$' | grep -o '\bgcc[a-zA-Z0-9:_.-]*' |\
  xargs -I {} echo "{}" hold | dpkg --set-selections

RUN mkdir -p ${HOME_DIR}
WORKDIR ${HOME_DIR}
ADD code_builder/__init__.py code_builder/__init__.py
ADD docker/init.py init.py
ADD code_builder/utils/ utils
ADD code_builder/build_systems/ build_systems
ADD code_builder/wrappers/ wrappers
ADD code_builder/ci_systems/ ci_systems

# https://clang.debian.net/
# https://github.com/sylvestre/debian-clang/blob/master/clang-setup.sh
# force, since apt installed compilers

RUN ln -fs ${HOME_DIR}/wrappers/clang /usr/bin/cc\
  && ln -fs ${HOME_DIR}/wrappers/clang++ /usr/bin/c++\
  && ln -fs ${HOME_DIR}/wrappers/clang++ /usr/bin/cpp\
  && ln -fs ${HOME_DIR}/wrappers/clang /usr/bin/gcc\
  && ln -fs ${HOME_DIR}/wrappers/clang++ /usr/bin/g++

# replace all version of gcc
RUN cd ${HOME_DIR}/wrappers && ./replace_compilers.sh 4.6 4.7 4.8 4.9 5 6 7 8 9 10 11 12 13



# Check if gcc, g++ & cpp are actually clang
# RUN gcc --version|grep clang > /dev/null || exit 1
# RUN g++ --version|grep clang > /dev/null || exit 1
# RUN cpp --version|grep clang > /dev/null || exit 1

ENV CMAKE_EXPORT_COMPILE_COMMANDS=1
ENTRYPOINT ["python3", "-u", "init.py", "input.json"]
