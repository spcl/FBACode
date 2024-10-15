#!/usr/bash

function run_compilation() {

    compiler=$1
    # intercept compilation, ignore linking
    intercept_compilation=false
    intercept_compilation_no_c=true
    ARGS=()
    IR_FILES=()
    INPUT_ARGS=("$@")
    IGNORE_NEXT_ARG=false

    EMIT_AST_ARGS=()
    ACTUAL_COMPILE_ARGS=()

    for i in $(seq 1 $#); # 0-indexed, skipping first arg aka the compiler
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

        # if /tmp/fbacode_build_stage_flag doesn't exist then dont intercept
        # if [ ! -f /tmp/fbacode_build_stage_flag ]; then
        #     intercept_compilation=false
        #     intercep_compilation_no_c=false
        # fi

        if [[ "$var" == "-o" ]]; then
            IGNORE_NEXT_ARG=true
            next_i=$((i+1)) 
            next_var=${INPUT_ARGS[$next_i]}
            dirname=$(dirname -- "$next_var")
            filename=$(basename -- "$next_var")
            IR_FILES+=("${dirname}/${filename}.bc")
        # We want to override any printing dependencies flags, because we want to extract the dependencies ourselves
        # in the plain makefile format
        elif [[ "$var" == "-MF" ]] || [[ "$var" == "-MT" ]] || [[ "$var" == "MQ" ]]; then
            IGNORE_NEXT_ARG=true
        elif [[ "$var" == "-MD" ]] || [[ "$var" == "--write-dependencies" ]]; then
            # do nothing
            true
        elif [[ "$var" == "-M" ]] || [[ "$var" == "--dependencies" ]]; then
            # do nothing
            true
        elif [[ "$var" == "-MG" ]] || [[ "$var" == "--print-missing-file-dependencies" ]]; then
            # do nothing
            true
        elif [[ "$var" == "-MM" ]] || [[ "$var" == "--user-dependencies" ]]; then
            # do nothing
            true
        elif [[ "$var" == "-MMD" ]] || [[ "$var" == "--write-user-dependencies" ]]; then
            # do nothing
            true
        elif [[ "$var" == "-MP" ]] || [[ "$var" == "-MV" ]]; then
            # do nothing
            true
        elif [[ "$IGNORE_NEXT_ARG" == "true" ]]; then
            # Skiping this argument, resetting the flag
            IGNORE_NEXT_ARG=false
        else
            EMIT_AST_ARGS+=("$var")
        fi

        if [[ $var == *"[=W]maybe-unitialized" ]]; then
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
        else
            # adding argument to list
            ACTUAL_COMPILE_ARGS+=("$var")
        fi

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

    echo "${@:2}"  >> /home/fba_code/build/wrapper-fun.log
    if [ "$intercept_compilation" == true ]; then
        echo "-Qunused-arguments ${EMIT_AST_ARGS[@]} ${OMIT_ERRORS_ARGS[@]}" >> /home/fba_code/build/wrapped_args.log
        shopt -s nocasematch
        # if there are multiple input files, -emit-llvm would faile with the -o option
        #  || true because we want to continue, even if the command fails
    
        # if the target file is in tmp folder, then skip...
        printf "==========================\n" >> /home/fba_code/build/source-files-$$.log
        command_output=$(extract-source-files $(pwd) ${compiler} "${ACTUAL_COMPILE_ARGS[@]}" "${OMIT_ERRORS_ARGS[@]}" 2> /dev/null | tee -a /home/fba_code/build/source-files-$$.log)
        # printf "$command_output" >> /home/fba_code/build/source-files-$$.log
        if [[ ! "$command_output" == *"/tmp"* && ! "$command_output" == *"/conftest"* ]]; then
            printf "$$ does not contain temp\n" >> /home/fba_code/build/source-files-$$.log

            ${compiler} -Qunused-arguments -emit-llvm -c "${EMIT_AST_ARGS[@]}" "${OMIT_ERRORS_ARGS[@]}" > /dev/null 2>&1 || true
            ${compiler} -Qunused-arguments -emit-ast "${EMIT_AST_ARGS[@]}" "${OMIT_ERRORS_ARGS[@]}" 2>> /home/fba_code/build/emit-ast.stderr 1>> /home/fba_code/build/emit-ast.stdout || true

            # take the header dependencies, pretty print into file, remove first line since it looks like "main.o: main.cpp"
            # https://stackoverflow.com/questions/1983048/passing-a-string-with-spaces-as-a-function-argument-in-bash
            echo "$(pwd)" >> /home/fba_code/build/header_dependencies/$$.log
            ${compiler} -Qunused-arguments -M "${EMIT_AST_ARGS[@]}" "${OMIT_ERRORS_ARGS[@]}" 1>> /home/fba_code/build/header_dependencies/$$.log 2> /dev/null || true
            printf "\n" >> /home/fba_code/build/header_dependencies/$$.log 
        else
            printf "$$ contains temp\n" >> /home/fba_code/build/source-files-$$.log
        fi
        printf "++++++++++++++++++++++++++++++++\n" >> /home/fba_code/build/source-files-$$.log

        # ${compiler} "${@:2}" "${OMIT_ERRORS_ARGS}"
        ${compiler} "${ACTUAL_COMPILE_ARGS[@]}" "${OMIT_ERRORS_ARGS[@]}"
        
    elif [ "$intercep_compilation_no_c" == true ]; then
        # echo "Run LLVM generation with flags, add -c manually: ${ARGS[@]}" > /dev/stderr
        echo "-Qunused-arguments ${EMIT_AST_ARGS[@]} ${OMIT_ERRORS_ARGS[@]}" >> /home/fba_code/build/wrapped_args.log

        printf "==========================\n" >> /home/fba_code/build/source-files-$$.log
        command_output=$(extract-source-files $(pwd) ${compiler} "${ACTUAL_COMPILE_ARGS[@]}" "${OMIT_ERRORS_ARGS[@]}" 2> /dev/null | tee -a /home/fba_code/build/source-files-$$.log)
        # command_output=$(extract-source-files ${compiler} \"${ACTUAL_COMPILE_ARGS[@]}\" \"${OMIT_ERRORS_ARGS[@]}\" 2> /dev/null)
        printf "$command_output" >> /home/fba_code/build/source-files-$$.log
        if [[ ! "$(command_output)" == *"/tmp"* ]]; then
            printf "$$ does not contain temp\n" >> /home/fba_code/build/source-files-$$.log
            
            ${compiler} -Qunused-arguments -emit-llvm "${EMIT_AST_ARGS[@]}" -c "${OMIT_ERRORS_ARGS[@]}" > /dev/null 2>&1 || true
            ${compiler} -Qunused-arguments -emit-ast "${EMIT_AST_ARGS[@]}" "${OMIT_ERRORS_ARGS[@]}" 2>> /home/fba_code/build/emit-ast.stderr 1>> /home/fba_code/build/emit-ast.stdout || true

            echo "$(pwd)" >> /home/fba_code/build/header_dependencies/$$.log
            ${compiler} -Qunused-arguments -M ${EMIT_AST_ARGS[@]} ${OMIT_ERRORS_ARGS[@]} 1>> /home/fba_code/build/header_dependencies/$$.log 2> /dev/null || true
            printf "\n" >> /home/fba_code/build/header_dependencies/$$.log 
        else
            printf "$$ contains temp\n" >> /home/fba_code/build/source-files-$$.log
        fi
        printf "++++++++++++++++++++++++++++++++\n" >> /home/fba_code/build/source-files-$$.log
        ${compiler} "${ACTUAL_COMPILE_ARGS[@]}" "${OMIT_ERRORS_ARGS[@]}"
    else
        #echo "Run linking with flags: "${IR_FILES[@]}""
        # echo "not generating llvm ir"
        ${compiler} "${ACTUAL_COMPILE_ARGS[@]}" "${OMIT_ERRORS_ARGS[@]}"
        #${LLVM_INSTALL_DIRECTORY}/bin/llvm-as "${IR_FILES[@]}"
    fi
}

# -Wno-error=implicit-function-declaration is needed because:
# https://www.redhat.com/en/blog/new-warnings-and-errors-clang-16
