from __future__ import (absolute_import, unicode_literals, division,
                        print_function)
import os
import glob
# For Python 2 and 3 compatibility
try:
    import configparser
except ImportError:
    import ConfigParser as configparser


def read_config(fname=None):
    '''Read a config file and return a dictionary of all entries'''

    config_output = {}

    Config = configparser.ConfigParser()

    if fname is None:
        fname = 'config.ini'

    Config.read(fname)

    # ---------- Set default values --------------------------------------

    config_output['projection'] = 'ARC'
    config_output['interpolation'] = 'linear'
    config_output['workdir'] = './'
    config_output['datadir'] = os.path.abspath(
        os.path.join(os.path.abspath(os.path.dirname(__file__)),
                     '..', '..', 'TEST_DATASET'))
    config_output['list_of_directories'] = '*'

    # --------------------------------------------------------------------

    # Read local information

    local_params = dict(Config.items('local'))

    config_output.update(local_params)

    # Read analysis information
    analysis_params = dict(Config.items('analysis'))

    config_output.update(analysis_params)

    config_output['list_of_directories'] = \
        [s for s in analysis_params['list_of_directories'].splitlines()
         if s.strip()]  # This last instruction eliminates blank lines

    # If the list of directories is not specified, or if a '*' symbol is used,
    # use glob in the datadir to determine the list

    if config_output['list_of_directories'] in ([], ['*'], '*'):
        config_output['list_of_directories'] = \
            [os.path.split(f)[1]  # return name without path
             for f in glob.glob(os.path.join(config_output['datadir'], '*'))
             if os.path.isdir(f)]  # only if it's a directory

    return config_output


def test_read_config():
    '''Test that config file are read.'''
    import os
    curdir = os.path.abspath(os.path.dirname(__file__))
    datadir = os.path.join(curdir, '..', '..', 'TEST_DATASET')

    fname = os.path.join(datadir, 'test_config.ini')

    config = read_config(fname)

    print('\n --- Test config file ---')
    for k in config.keys():
        print("{}: {}".format(k, config[k]))


def test_read_incomplete_config():
    '''Test that config file are read.'''
    import os
    curdir = os.path.abspath(os.path.dirname(__file__))
    datadir = os.path.join(curdir, '..', '..', 'TEST_DATASET')

    fname = os.path.join(datadir, 'test_config_incomplete.ini')

    config = read_config(fname)

    print('\n --- Test incomplete config file ---')
    for k in config.keys():
        print("{}: {}".format(k, config[k]))
