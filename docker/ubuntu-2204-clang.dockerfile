FROM ubuntu:22.04
# set as env, we are noninteractive in the container too
ENV DEBIAN_FRONTEND=noninteractive
# for tzdata, otherwise there will be a prompt
RUN echo "Europe/Zurich" > /etc/timezone

ARG CLANG_VERSION
RUN echo "building image for clang version ${CLANG_VERSION}"


ARG deps='apt-transport-https ca-certificates software-properties-common gpg-agent gnupg curl wget unzip' 
ARG soft="python3 python3-pip make libomp-${CLANG_VERSION}-dev texinfo \
build-essential fakeroot devscripts automake autotools-dev git sudo python2 \
libllvm${CLANG_VERSION} llvm-${CLANG_VERSION} llvm-${CLANG_VERSION}-dev \
llvm-${CLANG_VERSION}-runtime clang-${CLANG_VERSION} clang-tools-${CLANG_VERSION} \
libclang-common-${CLANG_VERSION}-dev libclang-${CLANG_VERSION}-dev libclang1-${CLANG_VERSION} \
clangd-${CLANG_VERSION} libc++-${CLANG_VERSION}-dev libc++abi-${CLANG_VERSION}-dev"
RUN apt-get update 
RUN apt-get install -y ${deps} --no-install-recommends
RUN curl https://apt.llvm.org/llvm-snapshot.gpg.key | apt-key add -
RUN add-apt-repository "deb http://apt.llvm.org/jammy/ llvm-toolchain-jammy main"
RUN add-apt-repository "deb http://apt.llvm.org/jammy/ llvm-toolchain-jammy-17 main"
RUN add-apt-repository "deb http://apt.llvm.org/jammy/ llvm-toolchain-jammy-18 main"
RUN add-apt-repository universe

# add the cmake repo
# RUN curl https://apt.kitware.com/keys/kitware-archive-latest.asc | apt-key add -
# RUN apt-add-repository 'deb https://apt.kitware.com/ubuntu/ focal main'

# install compilers and build systems
RUN apt-get update
RUN apt-get install -y ${soft} --no-install-recommends
RUN apt-get purge -y --auto-remove ${DEPS}
RUN ln -s /usr/bin/clang-${CLANG_VERSION} /usr/bin/clang
RUN ln -s /usr/bin/clang++-${CLANG_VERSION} /usr/bin/clang++
# install needed python modules
RUN python3 -m pip install pyyaml

# install python2 pip for travis
RUN curl https://bootstrap.pypa.io/pip/2.7/get-pip.py --output get-pip.py
# RUN curl https://bootstrap.pypa.io/2.7/get-pip.py --output get-pip.py
RUN python2 get-pip.py
RUN python2 -m pip install --upgrade pip
# install pyenv (needed for travis...)
RUN curl https://pyenv.run | bash
# so travis can use sudo
RUN useradd -m docker && echo "docker:docker" | chpasswd && adduser docker sudo

RUN pip3 install GitPython==3.1.42
# install conan
RUN pip3 install conan==2.2.2
RUN conan profile detect
RUN echo "tools.system.package_manager:mode=install" >> $(conan config home)/global.conf

# install latest version of CMake (hardcoded)
RUN mkdir /tmp/cmake-install && wget -qO- "https://cmake.org/files/v3.28/cmake-3.28.3-linux-x86_64.tar.gz" | tar --strip-components=1 -xz -C /tmp/cmake-install
RUN ln -s /tmp/cmake-install/bin/cmake /usr/bin/cmake
RUN ln -s /tmp/cmake-install/bin/ccmake /usr/bin/ccmake

# install latest version of ninja-build (hardcoded)
RUN wget -O /tmp/ninja-build.zip "https://github.com/ninja-build/ninja/releases/download/v1.11.1/ninja-linux.zip" && unzip /tmp/ninja-build.zip -d /usr/bin

ENV HOME_DIR /home/fba_code/
ENV SRC_DIR ${HOME_DIR}/code
ENV BUILD_DIR ${HOME_DIR}/build
ENV BITCODES_DIR ${HOME_DIR}/bitcodes

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


# # install cxx-langstat
# RUN git clone https://github.com/spcl/cxx-langstat.git
# RUN mkdir -p cxx-langstat/include/nlohmann && wget https://raw.githubusercontent.com/nlohmann/json/develop/single_include/nlohmann/json.hpp -O cxx-langstat/include/nlohmann/json.hpp
# RUN mkdir ./cxx-langstat/build && cd cxx-langstat/build && cmake -G "Ninja" -DCMAKE_CXX_COMPILER=clang++-${CLANG_VERSION} -DCMAKE_MAKE_PROGRAM=ninja -DCMAKE_C_COMPILER=clang-11 ../ && ninja
# # RUN ./cxx-langstat/build/cxx-langstat --version

# install cxx-langstat
RUN mkdir -p /opt/source/
RUN cd /opt/source && git clone https://github.com/spcl/cxx-langstat.git && cd cxx-langstat && git checkout cdragancea/clang18
ENV CXX_LANGSTAT_PROJECT_PATH=/opt/source/cxx-langstat
RUN mkdir -p ${CXX_LANGSTAT_PROJECT_PATH}/include/nlohmann && wget https://raw.githubusercontent.com/nlohmann/json/develop/single_include/nlohmann/json.hpp -O ${CXX_LANGSTAT_PROJECT_PATH}/include/nlohmann/json.hpp
RUN mkdir ${CXX_LANGSTAT_PROJECT_PATH}/build && cd ${CXX_LANGSTAT_PROJECT_PATH}/build && cmake -G "Ninja" -DCMAKE_CXX_COMPILER=clang++-${CLANG_VERSION} -DCMAKE_MAKE_PROGRAM=ninja -DCMAKE_C_COMPILER=clang-${CLANG_VERSION} -DCLANG_DIR=/usr/lib/llvm-${CLANG_VERSION}/lib/cmake/clang ../ && ninja
# RUN cp ${CXX_LANGSTAT_PROJECT_PATH}/build/cxx-langstat ${LLVM_PROJECT_PATH}/build/bin/cxx-langstat
# RUN ./cxx-langstat/build/cxx-langstat --version

# put the binaries somewhere accessible
# RUN mkdir ${HOME_DIR}/software
# RUN ln -fs ${LLVM_PROJECT_PATH}/build/bin/clang ${HOME_DIR}/software/clang
# RUN ln -fs ${LLVM_PROJECT_PATH}/build/bin/clang++ ${HOME_DIR}/software/clang++
# RUN ln -fs /usr/bin/clang-${CLANG_VERSION} ${HOME_DIR}/software/clang
# RUN ln -fs /usr/bin/clang++-${CLANG_VERSION} ${HOME_DIR}/software/clang++
# RUN ln -fs ${CXX_LANGSTAT_PROJECT_PATH}/build/cxx-langstat ${HOME_DIR}/software/cxx-langstat
# RUN ln -fs ${LLVM_PROJECT_PATH}/build/bin/cxx-langstat ${HOME_DIR}/software/cxx-langstat

RUN cp ${CXX_LANGSTAT_PROJECT_PATH}/build/cxx-langstat /usr/lib/llvm-${CLANG_VERSION}/bin
RUN ln -fs /usr/lib/llvm-${CLANG_VERSION}/bin/cxx-langstat /usr/bin/cxx-langstat
RUN mkdir -p ${HOME_DIR}/features
RUN ln -fs /usr/bin/clang++-${CLANG_VERSION} /usr/bin/clang++
RUN ln -fs /usr/bin/clang-${CLANG_VERSION} /usr/bin/clang

# Add the FBACode code
RUN mkdir -p ${HOME_DIR}
WORKDIR ${HOME_DIR}
ADD docker/init.py init.py
ADD code_builder/utils/ utils
ADD code_builder/build_systems/ build_systems
ADD code_builder/wrappers/ wrappers
ADD code_builder/ci_systems ci_systems
RUN mkdir ${HOME_DIR}/build

# fake travis commands so scripts don't fail
RUN ln -s "${HOME_DIR}/wrappers/travis_retry.sh" /usr/bin/travis_retry
RUN ln -s "${HOME_DIR}/wrappers/travis_cmd.sh" /usr/bin/travis_cmd
RUN ln -s "${HOME_DIR}/wrappers/exit0.sh" /usr/bin/travis_time_start
RUN ln -s "${HOME_DIR}/wrappers/exit0.sh" /usr/bin/travis_time_finish
RUN ln -s "${HOME_DIR}/wrappers/exit0.sh" /usr/bin/travis_terminate
RUN ln -s "${HOME_DIR}/wrappers/pass_cmd.sh" /usr/bin/travis_wait
RUN ln -s "${HOME_DIR}/wrappers/exit0.sh" /usr/bin/travis_assert


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
# RUN ${LLVM_PROJECT_PATH}/build/bin/clang --version || exit 1
# RUN ls ${HOME_DIR}/software/ || exit 1
# RUN ${HOME_DIR}/software/clang --version || exit 1
# RUN ls ${HOME_DIR}/wrappers/ || exit 1
# RUN ${HOME_DIR}/wrappers/clang --version || exit 1
# RUN which gcc
# RUN ls -alh /usr/bin/gcc
# RUN echo $CLANGCC
# RUN echo $CLANGCXX
# RUN gcc --version || exit 1
# RUN gcc --version|grep clang > /dev/null || exit 1
# RUN g++ --version|grep clang > /dev/null || exit 1
# RUN cpp --version|grep clang > /dev/null || exit 1
RUN cxx-langstat --version

ENTRYPOINT ["python3", "-u", "init.py", "input.json"]
