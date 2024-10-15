ARG CLANG_VERSION
FROM spcleth/fbacode:debian-bookworm-clang-base-${CLANG_VERSION}

ARG CLANG_VERSION
ENV CLANG_VERSION=${CLANG_VERSION}
# ENV BASE=$BASE
RUN echo "building image for clang version ${CLANG_VERSION}"

# # install cxx-langstat
# RUN mkdir -p /opt/source/
# RUN cd /opt/source && git clone https://github.com/spcl/cxx-langstat.git && cd cxx-langstat && git checkout cdragancea/clang18
# ENV CXX_LANGSTAT_PROJECT_PATH=/opt/source/cxx-langstat
# RUN mkdir -p ${CXX_LANGSTAT_PROJECT_PATH}/include/nlohmann && wget https://raw.githubusercontent.com/nlohmann/json/develop/single_include/nlohmann/json.hpp -O ${CXX_LANGSTAT_PROJECT_PATH}/include/nlohmann/json.hpp
# RUN mkdir ${CXX_LANGSTAT_PROJECT_PATH}/build && cd ${CXX_LANGSTAT_PROJECT_PATH}/build && cmake -G "Ninja" -DCMAKE_CXX_COMPILER=clang++-${CLANG_VERSION} -DCMAKE_MAKE_PROGRAM=ninja -DCMAKE_C_COMPILER=clang-${CLANG_VERSION} -DCLANG_DIR=/usr/lib/llvm-${CLANG_VERSION}/lib/cmake/clang ../ && ninja

# install cxx-langstat from einstein local source code
RUN mkdir -p /opt/source/
ADD cxx-langstat /opt/source/cxx-langstat
ENV CXX_LANGSTAT_PROJECT_PATH=/opt/source/cxx-langstat
RUN mkdir -p ${CXX_LANGSTAT_PROJECT_PATH}/build && cd ${CXX_LANGSTAT_PROJECT_PATH}/build && rm -rf ./* && cmake -G "Ninja" -DCMAKE_CXX_COMPILER=clang++-${CLANG_VERSION} -DCMAKE_MAKE_PROGRAM=ninja -DCMAKE_C_COMPILER=clang-${CLANG_VERSION} -DCLANG_DIR=/usr/lib/llvm-${CLANG_VERSION}/lib/cmake/clang ../ && ninja

ENV HOME_DIR /home/fba_code/
RUN mkdir -p ${HOME_DIR}
RUN mkdir -p ${HOME_DIR}/ast_archive
WORKDIR ${HOME_DIR}
# ADD code_builder/__init__.py code_builder/__init__.py
ADD code_analyzer/docker_entrypoint.py analysis_init.py
ADD code_builder/utils/ utils
ADD code_builder/build_systems/ build_systems
ADD code_builder/wrappers/ wrappers
# ADD code_builder/ci_systems/ ci_systems

# put the binaries somewhere accessible
# RUN mkdir ${HOME_DIR}/software
# RUN ln -fs ${LLVM_PROJECT_PATH}/build/bin/clang ${HOME_DIR}/software/clang
# RUN ln -fs ${LLVM_PROJECT_PATH}/build/bin/clang++ ${HOME_DIR}/software/clang++
# RUN ln -fs /usr/bin/clang-${CLANG_VERSION} ${HOME_DIR}/software/clang
# RUN ln -fs /usr/bin/clang++-${CLANG_VERSION} ${HOME_DIR}/software/clang++
# RUN ln -fs ${CXX_LANGSTAT_PROJECT_PATH}/build/cxx-langstat ${HOME_DIR}/software/cxx-langstat
# RUN ln -fs ${CXX_LANGSTAT_PROJECT_PATH}/build/cxx-langstat /usr/bin/cxx-langstat

RUN cp ${CXX_LANGSTAT_PROJECT_PATH}/build/cxx-langstat /usr/lib/llvm-${CLANG_VERSION}/bin
RUN ln -fs /usr/lib/llvm-${CLANG_VERSION}/bin/cxx-langstat /usr/bin/cxx-langstat
RUN mkdir -p ${HOME_DIR}/analyze


ENTRYPOINT ["python3", "-u", "analysis_init.py", "input.json"]
