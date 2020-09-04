#!/usr/bin/bash

function run_compilation() {

    compiler=$1
    # intercept compilation, ignore linking
    intercept_compilation=false
    intercept_compilation_no_c=true
    ARGS=()
    IR_FILES=()
    INPUT_ARGS=("$@")
    IGNORE_NEXT_ARG=false
    # echo "arguments: "
    for i in $(seq 1 $#);
    do
        var=${INPUT_ARGS[$i]}
        # echo $var
        #echo $intercept_compilation
        # why was it =~?
        if [[ "$var" == "-c" ]]; then
            intercept_compilation=true
            # intercept_compilation_no_c=false
        fi
        # match on an argument if it ends with .c, .cpp or .cxx
        if [[ "$var" =~ .*(\.c|\.cpp|\.cxx|\.cc)$  && "$intercept_compilation" == false ]]; then
            # echo "one of the input files is a source file!"
            intercept_compilation=true
            # intercept_compilation_no_c=true
        fi
        if [[ ! "$var" == "-o" ]]; then
            if ! ${IGNORE_NEXT_ARG}; then
                #echo "Add"
                ARGS+=("$var")
            else
                IGNORE_NEXT_ARG=false
            fi         
        else
            IGNORE_NEXT_ARG=true
            # ARGS+=("$var")
            i=$((i+1)) 
            var=${INPUT_ARGS[$i]}
            #echo "$var"
            dirname=$(dirname -- "$var")
            filename=$(basename -- "$var")
            filename="${filename%.*}"
            #echo "${dirname}/${filename}.ll"
            IR_FILES+=("${dirname}/${filename}.bc")
            # ARGS+=("${dirname}/${filename}.bc")
        fi
    done
    #echo ${ARGS[@]}
    #echo $intercept_compilation
    # TODO: also create AST files using -emit-ast flag
    if [ "$intercept_compilation" == true ]; then
        shopt -s nocasematch
        # echo "Run LLVM generation with flags: ${ARGS[@]}"
        # echo "first run this: ${compiler} ${@:2}"
        # echo "do compilation"
        ${compiler} "${@:2}"
        # echo "now emit llvm"
        ${compiler} -emit-llvm -c "${ARGS[@]}" # if there are multiple input files, -emit-llvm would faile with the -o option
        ${compiler} -emit-ast "${ARGS[@]}"
        # ${compiler} -emit-llvm "${ARGS[@]}"
        # ${compiler} -emit-llvm "${ARGS[@]}"
        #echo "${ARGS[@]}"
        #for var in "${ARGS[@]}"
        #do
        #    if [[ "$var" =~ ".cpp" ]] || [[ "$var" =~ ".c" ]] ; then
        #        dirname=$(dirname -- "$var")
        #        filename=$(basename -- "$var")
        #        filename="${filename%.*}"
        #        echo "Run LLVM generation with flags: ${ARGS[@]}"
        #        ${LLVM_INSTALL_DIRECTORY}/bin/${compiler} "${@:2}"
        #        ${LLVM_INSTALL_DIRECTORY}/bin/${compiler} -S -emit-llvm "${ARGS[@]}"
        #        echo "${LLVM_INSTALL_DIRECTORY}/bin/${compiler} -S -emit-llvm "${ARGS[@]}" "${IR_FILES[@]}""
        #        #${LLVM_INSTALL_DIRECTORY}/bin/clang "$@" 
        #        #${LLVM_INSTALL_DIRECTORY}/bin/clang -S -emit-llvm "${ARGS[@]}"
        #        #${LLVM_INSTALL_DIRECTORY}/bin/opt -load ${LLVM_TOOL_DIRECTORY}/libLLVMLoopStatistics.so -loop-statistics -loop-statistics-out-dir ${OUT_DIR} -loop-statistics-log-name "$filename" < "$filename.ll" > /dev/null
        #    fi
        #done
    elif [ "$intercep_compilation_no_c" ]; then
        # echo "Run LLVM generation with flags, add -c manually: ${ARGS[@]}"
        ${compiler} "${@:2}"
        ${compiler} -emit-llvm "${ARGS[@]}" -c
        ${compiler} -emit-ast "${ARGS[@]}"
    else
        #echo "Run linking with flags: "${IR_FILES[@]}""
        # echo "not generating llvm ir"
        ${compiler} "${@:2}"
        #${LLVM_INSTALL_DIRECTORY}/bin/llvm-as "${IR_FILES[@]}"
    fi
}
