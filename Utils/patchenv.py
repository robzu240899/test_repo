'''
Created on Apr 13, 2017

@author: Thomas
'''

import os
from subprocess32 import check_output, STDOUT

class EnvironmentPatcher(object):
    
    @classmethod 
    def patch(cls,path='/opt/python/current/env'):
        "Patch the current environment, os.environ, with the contents of the specified environment file."
        #based on snippet: http://stackoverflow.com/a/3505826/504550
        cmd = ['bash', '-c', 'source {path} && env'.format(path=path)]
    
        output = check_output(cmd, stderr=STDOUT, timeout=5)
    
        # proc_stdout is just a big string, not a file-like object
        # we can't iterate directly over its lines.
        for line in output.splitlines():
            (key, _, value) = line.partition("=")
            os.environ[key] = value