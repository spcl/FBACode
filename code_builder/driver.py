
from datetime import datetime
from sys import stdout, stderr
from configparser import ConfigParser
from os import path

from code_builder import logger

# https://stackoverflow.com/questions/5574702/how-to-print-to-stderr-in-python
def error_print(*args, **kwargs):
    print(*args, file=stderr, **kwargs)

def open_logfiles(parsed_args):
    timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    if parsed_args.out_to_file:
        output_log = logger.create_file_logger(
                filename = os.path.join(parsed_args.out_to_file, 'output'),
                time = timestamp, verbose = parsed_args.verbose)
        error_log = logger.create_file_logger(
                filename = os.path.join(parsed_args.out_to_file, 'error'),
                time = timestamp, verbose = parsed_args.verbose)
    else:
        output_log = logger.create_stream_logger(
                name = 'output',
                stream = stdout,
                verbose = parsed_args.verbose)
        error_log = logger.create_stream_logger(
                name = 'error',
                stream = stderr,
                verbose = parsed_args.verbose)
    return [output_log, error_log]

from collections import OrderedDict

# change default behavior of ConfigParser
# instead of overwriting sections with same key,
# accumulate the results
class multidict(OrderedDict):

    def __setitem__(self, key, val):
        if isinstance(val, dict):
            if key in self:
                self.update(key, {**self.get(key), **val})
                return
        OrderedDict.__setitem__(self, key, val)

def open_config(parsed_args, exec_dir):

    cfg = ConfigParser(dict_type=multidict, strict=False)
    default_cfg = parsed_args.config_file
    user_cfg = parsed_args.user_config_file
    # if file not provided, use the one located in top project directory
    if path.exists(default_cfg):
        default_cfg = path.join(exec_dir, default_cfg)
    if not path.exists(user_cfg):
        user_cfg = path.join(exec_dir, 'user.cfg')
    cfg.read([user_cfg, default_cfg])
    return cfg
