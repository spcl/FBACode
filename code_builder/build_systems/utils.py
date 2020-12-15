import subprocess
from sys import version_info
from subprocess import CalledProcessError, CompletedProcess


def decode(stream):
    if isinstance(stream, bytes) or isinstance(stream, bytearray):
        return stream.decode("utf-8")
    else:
        return stream


def run(command, cwd=None, stdout=None, stderr=None) -> CompletedProcess:
    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    if version_info.major >= 3 and version_info.minor >= 5:
        out = subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr)
        return CompletedProcess(
            out.args, out.returncode, decode(out.stdout), decode(out.stderr)
        )
    else:
        code = 0
        try:
            out = subprocess.check_output(command, cwd=cwd, stderr=subprocess.STDOUT)
        except CalledProcessError as e:
            code = e.returncode
            out = e.output
            return CompletedProcess(command, code, stderr=decode(out))
        return CompletedProcess(command, code, stdout=decode(out))
