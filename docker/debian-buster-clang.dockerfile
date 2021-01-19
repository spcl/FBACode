FROM debian:buster
# set as env, we are noninteractive in the container too
ENV DEBIAN_FRONTEND=noninteractive
# do not run tests on builds (does not work for all pkgs)
ENV DEB_BUILD_OPTIONS=nocheck
# for tzdata, otherwise there will be a prompt
RUN echo "Europe/Zurich" > /etc/timezone

ARG CLANG_VERSION
RUN echo "building image for clange version ${CLANG_VERSION}"

# add source code repos to debian
RUN rm /etc/apt/sources.list
# TODO: do this with sed or something
COPY docker/sources_buster.list /etc/apt/sources.list




ARG deps='software-properties-common curl gpg-agent gnupg' 
ARG soft="python3 cmake make clang-${CLANG_VERSION} libomp-${CLANG_VERSION}-dev \
clang++-${CLANG_VERSION} llvm-${CLANG_VERSION} llvm-${CLANG_VERSION}-dev texinfo \
build-essential fakeroot devscripts wget dh-make"
RUN echo ${CLANG_VERSION}
RUN apt-get update 
RUN apt-get install -y ${deps} --no-install-recommends --force-yes
RUN curl https://apt.llvm.org/llvm-snapshot.gpg.key | apt-key add -
# https://apt.llvm.org/
RUN add-apt-repository "deb http://apt.llvm.org/buster/ llvm-toolchain-buster main"
RUN add-apt-repository "deb http://apt.llvm.org/buster/ llvm-toolchain-buster-9 main"
RUN add-apt-repository "deb http://apt.llvm.org/buster/ llvm-toolchain-buster-10 main"
RUN add-apt-repository "deb http://apt.llvm.org/buster/ llvm-toolchain-buster-11 main"
RUN apt-get update
RUN apt-get install -y ${soft} --no-install-recommends --force-yes
RUN apt-get purge -y --auto-remove ${DEPS}
RUN ln -s /usr/bin/clang-${CLANG_VERSION} /usr/bin/clang
RUN ln -s /usr/bin/clang++-${CLANG_VERSION} /usr/bin/clang++

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

RUN apt install --yes --no-install-recommends --force-yes qt5-qmake
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
RUN cd ${HOME_DIR}/wrappers && ./replace_compilers.sh 4.6 4.7 4.8 4.9 5 6 7 8 9 10



# Check if gcc, g++ & cpp are actually clang
RUN gcc --version|grep clang > /dev/null || exit 1
RUN g++ --version|grep clang > /dev/null || exit 1
RUN cpp --version|grep clang > /dev/null || exit 1

ENTRYPOINT ["python3", "-u", "init.py", "input.json"]
