#!/usr/bin/env python2.7

# Copyright 2013 Virantha Ekanayake All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.



"""
    Wrap ImageMagick calls.  Yes, this is ugly.
"""

import subprocess
import sys, os
import logging
import glob
import functools
import signal

from multiprocessing import Pool

TIMEOUT = 500

# Ugly hack to pass in object method to the multiprocessing library
# From http://www.rueckstiess.net/research/snippets/show/ca1d7d90
# Basically gets passed in a pair of (self, arg), and calls the method
def unwrap_self(arg, **kwarg):
    return PyPreprocess._run_preprocess(*arg, **kwarg)

class TimeoutError(Exception):
    pass


def handler(signum, frame):
    raise TimeoutError()

def which(program):
    import os
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

class PyPreprocess(object):
    """Class to wrap all the ImageMagick convert calls"""
    def __init__(self, config):
        self.msgs = {
                'CV_FAILED': 'convert execution failed',
            }
        self.threads = config.get('threads', 4)

    def _warn(self, msg): # pragma: no cover
        print("WARNING: %s" % msg)

    def cmd(self, cmd_list):
        if isinstance(cmd_list, list):
            cmd_list = ' '.join(cmd_list)
        logging.debug("Running cmd: %s" % cmd_list)
        try:
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(TIMEOUT)
            proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, preexec_fn=os.setsid)
            pid = proc.pid
            (out, error) = proc.communicate()
            signal.alarm(0)
            logging.debug(out)
            return out
        except subprocess.CalledProcessError as e:
            print e.output
            self._warn("Could not run command %s" % cmd_list)
        except TimeoutError, te:
            print "Timeout exceeded PID", pid, cmd_list
            os.killpg(pid, signal.SIGTERM)
            # os.kill(pid, signal.SIGTERM)
        finally:
            signal.alarm(0)

        if proc:
            proc.terminate()
            proc.kill()
            print "Killing processes"

        return None

            

    def _run_preprocess(self,  in_filename):
        basename, filext = os.path.splitext(in_filename)
        out_filename = '%s_preprocess%s' % (basename, filext)
        #-respect-parenthesis \( -clone 0 -colorspace gray -negate -lat 15x5+5% -contrast-stretch 0 \) -compose copy_opacity -composite -opaque none +matte -modulate 100,50 -adaptive-blur 2.0 -sharpen 0x1 
        # When using Windows, can't use backslash parenthesis in the shell, so omit the backslash
        if str(os.name) == 'nt':
            backslash = ''
        else:
            backslash = '\\'

        convert = which('convert');
        c = [convert,
                '"%s"' % in_filename,
                '-respect-parenthesis',
                #'\\( $setcspace -colorspace gray -type grayscale \\)',
                backslash+'(',
                '-clone 0',
                '-colorspace gray -negate -lat 15x15+5\% -contrast-stretch 0',
                backslash+') -compose copy_opacity -composite -opaque none +matte -modulate 100,100',
                #'-adaptive-blur 1.0',
                '-blur 1x1',
                #'-selective-blur 4x4+5%',
                '-adaptive-sharpen 0x2',
                '-negate -define morphology:compose=darken -morphology Thinning Rectangle:1x30+0+0 -negate ',  # Removes vertical lines >=60 pixes, reduces widht of >30 (oherwise tesseract completely ignores text close to vertical lines in a table)
                '"%s"' % (out_filename)
                ]
        logging.info("Preprocessing image %s for better OCR" % in_filename)
        res = self.cmd(c)

        if res is None:
            return in_filename
        else:
            # Make sure the convert process did not die on us
            if os.path.isfile(out_filename):
                print "Filename does not exist: ", out_filename, " using ", in_filename
                return out_filename

            return in_filename

    def preprocess(self, in_filenames):
        fns = in_filenames

        pool = Pool(processes=self.threads)
        logging.info("Starting preprocessing parallel execution")
        preprocessed_filenames = pool.map(unwrap_self, zip([self]*len(fns),fns))
        pool.close()
        pool.join()
        logging.info ("Completed preprocessing")
        return preprocessed_filenames




