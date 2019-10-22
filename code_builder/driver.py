
from datetime import datetime
from sys import stdout, stderr, exit
from configparser import ConfigParser
from os import path

import logger

def info(*args, **kwargs):
    print(*args, file=stdout, **kwargs)
# https://stackoverflow.com/questions/5574702/how-to-print-to-stderr-in-python
def error(*args, **kwargs):
    print(*args, file=stderr, **kwargs)

def open_logfiles(cfg, name, timestamp=''):
    verbose = cfg['output']['verbose']
    if 'file' in cfg['output']:
        output_log = logger.create_file_logger(
                filename = "%s_%s" % (path.join(cfg['output']['file'], 'output'), name),
                time = timestamp, verbose = verbose)
        error_log = logger.create_file_logger(
                filename = "%s_%s" % (path.join(cfg['output']['file'], 'error'), name),
                time = timestamp, verbose = verbose)
    else:
        output_log = logger.create_stream_logger(
                name = 'output',
                stream = stdout,
                verbose = verbose)
        error_log = logger.create_stream_logger(
                name = 'error',
                stream = stderr,
                verbose = verbose)
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
    cfg_file = path.join(exec_dir, default_cfg)
    # Main config file
    if path.exists(default_cfg):
        info('Opening config file %s' % default_cfg)
    # if file not provided, use the one located in top project directory
    elif path.exists(path.join(exec_dir, default_cfg)):
        default_cfg = path.join(exec_dir, default_cfg)
        info('Opening default config file %s' % default_cfg)
    else:
        error('Config file %s not found! Abort.' % default_cfg)
        exit(1)

    # User config file
    if path.exists(user_cfg):
        info('Opening user config file %s' % user_cfg)
    # if file not provided, use the one located in top project directory
    elif path.exists(path.join(exec_dir, user_cfg)):
        user_cfg = path.join(exec_dir, user_cfg)
        info('Opening default user config file %s' % user_cfg)
    else:
        error('User config file %s not found! Continue.' % user_cfg)

    cfg.read([user_cfg, default_cfg])
    return cfg
