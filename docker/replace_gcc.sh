
# https://clang.debian.net/
# https://github.com/sylvestre/debian-clang/blob/master/clang-setup.sh
ln -s ${HOME_DIR}/wrappers/clang /usr/bin/cc\
  && ln -s ${HOME_DIR}/wrappers/clang++ /usr/bin/c++\
  && ln -s ${HOME_DIR}/wrappers/clang /usr/bin/gcc\
  && ln -s ${HOME_DIR}/wrappers/clang++ /usr/bin/g++

apt search '^gcc-[0-9]*[.]*[0-9]*$' | grep -o '\bgcc[a-zA-Z0-9:_.-]*' |\
  xargs -I {} echo "{}" hold | dpkg --set-selections
apt search '^g++-[0-9]*[.]*[0-9]*$' | grep -o '\bg++[a-zA-Z0-9:_.-]*' |\
  xargs -I {} echo "{}" hold | dpkg --set-selections
