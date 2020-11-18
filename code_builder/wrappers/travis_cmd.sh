#!/bin/bash

assert= 
output= 
display= 
retry= 
timing= 
cmd= 
result= 

cmd=$1
TRAVIS_CMD=$cmd
shift

while true; do
    case "$1" in
        --assert)  assert=true; shift ;;
        --echo)    output=true; shift ;;
        --display) display=$2;  shift 2;;
        --retry)   retry=true;  shift ;;
        --timing)  timing=true; shift ;;
        *) break ;;
    esac
done

    if [[ -n "$timing" ]]; then
        travis_time_start
    fi

if [[ -n "$output" ]]; then
    echo "\$ ${display:-$cmd}"
fi

if [[ -n "$retry" ]]; then
    travis_retry eval "$cmd"
else
    eval "$cmd"
fi
result=$?

if [[ -n "$timing" ]]; then
    travis_time_finish
fi

if [[ -n "$assert" ]]; then
    travis_assert $result
fi

exit $result
