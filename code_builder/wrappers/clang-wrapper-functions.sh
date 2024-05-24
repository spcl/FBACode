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
        
        # flag already present, change nothing
        if [[ "$var" == "-emit-llvm" ]] || [[ "$var" == "-emit-ast" ]]; then
            intercept_compilation=false
            intercep_compilation_no_c=false
            break
        elif [[ "$var" == "-c" ]]; then
            intercept_compilation=true
            # intercept_compilation_no_c=false
        # match on an argument if it ends with .c, .cpp or .cxx
        elif [[ "$var" =~ .*(\.c|\.cpp|\.cxx|\.cc)$  && "$intercept_compilation" == false ]]; then
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

        # remove gcc errors that are not recognized by clang
        elif [[ $var == *"[=W]maybe-unitialized" ]]; then
        # elif [[ "$var" == "-Wno-error=maybe-uninitialized"]] || [[ "$var" == "-Wmaybe-uninitialized"]] || [[ "$var" == "-Werror=maybe_unitialized"]]; then
            # -Wmaybe-unitialized is a gcc warning flag that is not supported by clang
            continue
        elif [[ "$var" == *"[W=]noexcept" ]]; then
            # -Wnoexcept is a gcc warning flag that is not supported by clang
            continue
        elif [[ "$var" == *"[W=]strict-null-sentinel" ]]; then
            # -Wstrict-null-sentinel is a gcc warning flag that is not supported by clang
            continue
        elif [[ "$var" == *"[W=]logical-op" ]]; then
            continue


        # elif [[ "$var" == "-Wno-error=implicit-int"]] || [[ "$var" == "-Wimplicit-int"]] || [[ "$var" == "-Werror=implicit-int"]]; then
        #     # -Wimplicit-int is a warning that was upgraded to an error in clang 16
        #     continue
        # elif [[ "$var" == "-Wno-error=implicit-function-declaration"]] || [[ "$var" == "-Wimplicit-function-declaration"]] || [[ "$var" == "-Werror=implicit-function-declaration"]]; then
        #     # -Wimplicit-function-declaration is a warning that was upgraded to an error in clang 16
        #     ARGS+=
        #     continue
        # elif [[ "$var" == "-Wno-error=incompatible-function-pointer-types"]] || [[ "$var" == "-Wincompatible-function-pointer-types"]] || [[ "$var" == "-Werror=incompatible-function-pointer-types"]]; then
        #     # -Wincompatible-function-pointer-types is a gcc warning flag that is not supported by clang
        #     continue
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

    # These warning flags were upgraded to errors in clang 16. They crash the build process.
    # The GCC compiler doesn't recognized them as errors, so the build would normally pass.
    OMIT_ERRORS_ARGS=""

    OMIT_ERRORS_ARGS+=("-Wno-error=implicit-function-declaration")
    OMIT_ERRORS_ARGS+=("-Wno-error=implicit-int")
    OMIT_ERRORS_ARGS+=("-Wno-error=int-conversion")
    OMIT_ERRORS_ARGS+=("-Wno-error=incompatible-function-pointer-types")
    OMIT_ERRORS_ARGS+=("-Wno-error=narrowing")
    OMIT_ERRORS_ARGS+=("-Wno-error=strict-prototypes")
    OMIT_ERRORS_ARGS+=("-Wno-error=unused-but-set-variable")
    OMIT_ERRORS_ARGS+=("-Wno-error=enum-constexpr-conversion")

    #echo ${ARGS[@]}
    #echo $intercept_compilation
    # TODO: also create AST files using -emit-ast flag
    # echo "######################## clang call" >> /home/fba_code/build/wrapper-fun.log
    echo "${@:2}"  >> /home/fba_code/build/wrapper-fun.log
    if [ "$intercept_compilation" == true ]; then
        shopt -s nocasematch
        # echo "Run LLVM generation with flags: ${ARGS[@]}" > /dev/stderr
        # echo "first run this: ${compiler} ${@:2}" > /dev/stderr
        # echo "do compilation"
        # echo "now emit llvm"
        # if there are multiple input files, -emit-llvm would faile with the -o option
        #  || true because we want to continue, even if the command fails
        ${compiler} -Qunused-arguments -emit-llvm -c "${ARGS[@]}" "${OMIT_ERRORS_ARGS}" > /dev/null 2>&1 || true
        ${compiler} -Qunused-arguments -emit-ast "${ARGS[@]}" "${OMIT_ERRORS_ARGS}" > /dev/null 2>&1 || true
        # -ast-print-xml seems to be deprecated
        # ${compiler} -Qunused-arguments -ast-print-xml "${ARGS[@]}"
        ${compiler} "${@:2}" "${OMIT_ERRORS_ARGS}"
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
    elif [ "$intercep_compilation_no_c" == true ]; then
        # echo "Run LLVM generation with flags, add -c manually: ${ARGS[@]}" > /dev/stderr
        ${compiler} -Qunused-arguments -emit-llvm "${ARGS[@]}" -c "${OMIT_ERRORS_ARGS}" > /dev/null 2>&1 || true
        ${compiler} -Qunused-arguments -emit-ast "${ARGS[@]}" "${OMIT_ERRORS_ARGS}" > /dev/null 2>&1 || true
        ${compiler} "${@:2}" "${OMIT_ERRORS_ARGS}"
    else
        #echo "Run linking with flags: "${IR_FILES[@]}""
        # echo "not generating llvm ir"
        ${compiler} "${@:2}" "${OMIT_ERRORS_ARGS}"
        #${LLVM_INSTALL_DIRECTORY}/bin/llvm-as "${IR_FILES[@]}"
    fi
}

# -Wno-error=implicit-function-declaration is needed because:
# https://www.redhat.com/en/blog/new-warnings-and-errors-clang-16
