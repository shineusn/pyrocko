from __future__ import print_function
import sys

if sys.version_info < (2, 6) or (3, 0) <= sys.version_info:
    sys.exit('This version of Pyrocko requires Python version >=2.6 and <3.0')
try:
    import numpy
except ImportError:
    class numpy():
        def __init__(self):
            pass

        @classmethod
        def get_include(self):
            return ''

import os
import time
import shutil
import tempfile
from os.path import join as pjoin
import os.path as op

from distutils.core import setup, Extension
from distutils.cmd import Command
from distutils.command.build_py import build_py
from distutils.command.build_ext import build_ext
from distutils.command.install import install


class NotInAGitRepos(Exception):
    pass


def git_infos():
    '''Query git about sha1 of last commit and check if there are local \
       modifications.'''

    from subprocess import Popen, PIPE
    import re

    def q(c):
        return Popen(c, stdout=PIPE).communicate()[0]

    if not os.path.exists('.git'):
        raise NotInAGitRepos()

    sha1 = q(['git', 'log', '--pretty=oneline', '-n1']).split()[0]
    sha1 = re.sub('[^0-9a-f]', '', sha1)
    sstatus = q(['git', 'status'])
    local_modifications = bool(re.search(r'^#\s+modified:', sstatus,
                                         flags=re.M))
    return sha1, local_modifications


def bash_completions_dir():
    from subprocess import Popen, PIPE

    def q(c):
        return Popen(c, stdout=PIPE).communicate()[0]

    try:
        d = q(['pkg-config', 'bash-completion', '--variable=completionsdir'])
        return d.strip().decode('utf-8')
    except:
        return None


def make_info_module(packname, version):
    '''Put version and revision information into file src/info.py.'''

    sha1, local_modifications = None, None
    combi = '%s-%s' % (packname, version)
    try:
        sha1, local_modifications = git_infos()
        combi += '-%s' % sha1
        if local_modifications:
            combi += '-modified'

    except (OSError, NotInAGitRepos):
        pass

    datestr = time.strftime('%Y-%m-%d_%H:%M:%S')
    combi += '-%s' % datestr

    s = '''# This module is automatically created from setup.py
git_sha1 = %s
local_modifications = %s
version = %s
long_version = %s  # noqa
installed_date = %s
''' % tuple([repr(x) for x in (
        sha1, local_modifications, version, combi, datestr)])

    try:
        f = open(pjoin('src', 'info.py'), 'w')
        f.write(s)
        f.close()
    except:
        pass


def make_prerequisites():
    from subprocess import check_call
    try:
        check_call(['sh', 'prerequisites/prerequisites.sh'])
    except:
        sys.exit('error: failed to build the included prerequisites with '
                 '"sh prerequisites/prerequisites.sh"')


def find_pyrocko_installs():
    found = []
    seen = set()
    orig_sys_path = sys.path
    for p in sys.path:

        ap = op.abspath(p)
        if ap == op.abspath('.'):
            continue

        if ap in seen:
            continue

        seen.add(ap)

        sys.path = [p]

        try:
            import pyrocko
            dpath = op.dirname(op.abspath(pyrocko.__file__))
            x = (pyrocko.installed_date, p, dpath,
                 pyrocko.long_version)
            found.append(x)
            del sys.modules['pyrocko']
            del sys.modules['pyrocko.info']
        except ImportError:
            pass

    sys.path = orig_sys_path
    return found


def print_installs(found, file):
    print(
        '\nsys.path configuration is: \n  %s\n' % '\n  '.join(sys.path),
        file=file)

    dates = sorted([xx[0] for xx in found])
    i = 1

    for (installed_date, p, installed_path, long_version) in found:
        oldnew = ''
        if len(dates) >= 2:
            if installed_date == dates[0]:
                oldnew = ' (oldest)'

            if installed_date == dates[-1]:
                oldnew = ' (newest)'

        print('''Pyrocko installation #%i:
  date installed: %s%s
  version: %s
  path: %s
''' % (i, installed_date, oldnew, long_version, installed_path), file=file)
        i += 1


def check_multiple_install():
    found = find_pyrocko_installs()
    e = sys.stderr

    dates = sorted([xx[0] for xx in found])

    if len(found) > 1:
        print_installs(found, e)

    if len(found) > 1:
        print(
            '''Installation #1 is used with default sys.path configuration.

WARNING: Multiple installations of Pyrocko are present on this system.''',
            file=e)
        if found[0][0] != dates[-1]:
            print('WARNING: Not using newest installed version.', file=e)


def check_pyrocko_install_compat():
    found = find_pyrocko_installs()
    if len(found) == 0:
        return

    expected_submodules = ['gui', 'dataset', 'client',
                           'streaming', 'io', 'model']

    installed_date, p, install_path, long_version = found[0]

    installed_submodules = [d for d in os.listdir(install_path)
                            if op.isdir(op.join(install_path, d))]

    if any([ed in installed_submodules for ed in expected_submodules]):

        print_installs(found, sys.stdout)

        print('''\n
###############################################################################
WARNING: Found an newer Python 2/3 compatible Pyrocko installation!

Please purge the new installation and the 'build' directory before installing
this older version:

    sudo rm -rf '%s' build

###############################################################################
''' % install_path)

        sys.exit(1)


class CheckInstalls(Command):
    description = '''check for multiple installations of Pyrocko'''
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        check_multiple_install()


class Uninstall(Command):
    description = 'delete installations of Pyrocko known to the invoked ' \
                  'Python interpreter'''

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        found = find_pyrocko_installs()
        print_installs(found, sys.stdout)

        if found:
            print('''
Use the following commands to remove the Pyrocko installation(s) known to the
currently running Python interpreter:

  sudo rm -rf build''')

            for _, _, install_path, _ in found:
                print('  sudo rm -rf "%s"' % install_path)

            print()

        else:
            print('''
No Pyrocko installations found with the currently running Python interpreter.
''')


class CustomInstallCommand(install):
    def run(self):
        check_pyrocko_install_compat()
        install.run(self)
        check_multiple_install()
        bd_dir = bash_completions_dir()
        if bd_dir:
            try:
                shutil.copy('extras/pyrocko', bd_dir)
                print('Installing pyrocko bash_completion to "%s"' % bd_dir)
            except:
                print(
                    'Could not install pyrocko bash_completion to "%s" '
                    '(continuing without)'
                    % bd_dir)


packname = 'pyrocko'
version = '0.3'

subpacknames = [
    'pyrocko.snufflings',
    'pyrocko.gf',
    'pyrocko.fomosto',
    'pyrocko.fdsn',
    'pyrocko.topo',
    'pyrocko.fomosto_report',
]


class double_install_check_cls(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        check_multiple_install()



class Prereqs(Command):
    description = '''Install prerequisites'''
    user_options = [
        ('force-yes', None, 'Do not ask for confirmation to install')]

    def initialize_options(self):
        self.force_yes = False

    def finalize_options(self):
        pass

    def run(self):

        from subprocess import Popen, PIPE, STDOUT
        import platform

        distribution = platform.linux_distribution()[0].lower().rstrip()
        distribution = 'debian' if distribution == 'ubuntu' else distribution
        fn = 'prerequisites/prerequisites_%s.sh' % distribution

        if not self.force_yes:
            confirm = raw_input('Execute: %s \n\
proceed? [y/n]' % open(fn, 'r').read())
            if not confirm.lower() == 'y':
                sys.exit(0)

        p = Popen(['sh', fn], stdin=PIPE, stdout=PIPE, stderr=STDOUT,
                  shell=False)

        while p.poll() is None:
            print(p.stdout.readline().rstrip())
        print(p.stdout.read())


class custom_build_py(build_py):
    def run(self):
        make_info_module(packname, version)
        build_py.run(self)


class custom_build_ext(build_ext):
    def run(self):
        make_prerequisites()
        build_ext.run(self)


class custom_build_app(build_ext):
    def run(self):
        self.make_app()

    def make_app(self):
        import glob
        import os
        import shutil
        from setuptools import setup

        APP = ['apps/snuffler']
        DATA_FILES = []
        OPTIONS = {
            'argv_emulation': True,
            'iconfile': 'src/data/snuffler.icns',
            'packages': 'pyrocko',
            'excludes': [
                'PyQt4.QtDesigner',
                'PyQt4.QtScript',
                'PyQt4.QtScriptTools',
                'PyQt4.QtTest',
                'PyQt4.QtCLucene',
                'PyQt4.QtDeclarative',
                'PyQt4.QtHelp',
                'PyQt4.QtSql',
                'PyQt4.QtTest',
                'PyQt4.QtXml',
                'PyQt4.QtXmlPatterns',
                'PyQt4.QtMultimedia',
                'PyQt4.phonon',
                'matplotlib.tests',
                'matplotlib.testing'],
            'plist': 'src/data/Info.plist'}

        setup(
            app=APP,
            data_files=DATA_FILES,
            options={'py2app': OPTIONS},
            setup_requires=['py2app'],
        )

        # Manually delete files which refuse to be ignored using 'excludes':
        want_delete = glob.glob(
            'dist/snuffler.app/Contents/Frameworks/libvtk*')

        map(os.remove, want_delete)

        want_delete_dir = glob.glob(
            'dist/Snuffler.app/Contents/Resources/lib/python2.7/'
            'matplotlib/test*')
        map(shutil.rmtree, want_delete_dir)


def _check_for_openmp():
    """Check  whether the default compiler supports OpenMP.
    This routine is adapted from pynbody // yt.
    Thanks to Nathan Goldbaum and Andrew Pontzen.
    """
    import distutils.sysconfig
    import subprocess

    tmpdir = tempfile.mkdtemp(prefix='pyrocko')
    compiler = os.environ.get(
      'CC', distutils.sysconfig.get_config_var('CC')).split()[0]

    # Attempt to compile a test script.
    # See http://openmp.org/wp/openmp-compilers/
    tmpfile = pjoin(tmpdir, 'check_openmp.c')
    with open(tmpfile, 'w') as f:
        f.write('''
#include <omp.h>
#include <stdio.h>
int main() {
    #pragma omp parallel
    printf("Hello from thread %d", omp_get_thread_num());
}
''')

    try:
        with open(os.devnull, 'w') as fnull:
            exit_code = subprocess.call([compiler, '-fopenmp', '-o%s'
                                         % pjoin(tmpdir, 'check_openmp'),
                                        tmpfile],
                                        stdout=fnull, stderr=fnull)
    except OSError:
        exit_code = 1
    finally:
        shutil.rmtree(tmpdir)

    if exit_code == 0:
        print ('Continuing your build using OpenMP...')
        return True

    import multiprocessing
    import platform
    if multiprocessing.cpu_count() > 1:
        print('''WARNING
OpenMP support is not available in your default C compiler, even though
your machine has more than one core available.
Some routines in pyrocko are parallelized using OpenMP and these will
only run on one core with your current configuration.
''')
        if platform.uname()[0] == 'Darwin':
            print('''Since you are running on Mac OS, it's likely that the problem here
is Apple's Clang, which does not support OpenMP at all. The easiest
way to get around this is to download the latest version of gcc from
here: http://hpc.sourceforge.net. After downloading, just point the
CC environment variable to the real gcc and OpenMP support should
get enabled automatically. Something like this -
sudo tar -xzf /path/to/download.tar.gz /
export CC='/usr/local/bin/gcc'
python setup.py clean
python setup.py build
''')
    print ('Continuing your build without OpenMP...')
    return False


if _check_for_openmp():
    omp_arg = ['-fopenmp']
    omp_lib = ['-lgomp']
else:
    omp_arg = []
    omp_lib = []

setup(
    cmdclass={
        'install': CustomInstallCommand,
        'build_py': custom_build_py,
        'py2app': custom_build_app,
        'build_ext': custom_build_ext,
        'double_install_check': double_install_check_cls,
        'prereqs': Prereqs,
        'uninstall': Uninstall,
    },

    name=packname,
    version=version,
    description='An open source toolbox and library for seismology.',
    author='The Pyrocko Developers',
    author_email='info@pyrocko.org',
    url='http://pyrocko.org',
    packages=[packname] + subpacknames,
    package_dir={'pyrocko': 'src'},
    ext_package=packname,
    ext_modules=[
        Extension(
            'util_ext',
            extra_compile_args=['-Wextra'],
            sources=[pjoin('src', 'util_ext.c')]),

        Extension(
            'signal_ext',
            include_dirs=[numpy.get_include()],
            extra_compile_args=['-Wextra'],
            sources=[pjoin('src', 'signal_ext.c')]),

        Extension(
            'mseed_ext',
            include_dirs=[numpy.get_include(), 'libmseed'],
            library_dirs=['libmseed'],
            libraries=['mseed'],
            extra_compile_args=['-Wextra'],
            sources=[pjoin('src', 'mseed_ext.c')]),

        Extension(
            'evalresp_ext',
            include_dirs=[numpy.get_include(), 'evalresp-3.3.0/include'],
            library_dirs=['evalresp-3.3.0/lib'],
            libraries=['evresp'],
            extra_compile_args=['-Wextra'],
            sources=[pjoin('src', 'evalresp_ext.c')]),

        Extension(
            'ims_ext',
            include_dirs=[numpy.get_include()],
            extra_compile_args=['-Wextra'],
            sources=[pjoin('src', 'ims_ext.c')]),

        Extension(
            'datacube_ext',
            include_dirs=[numpy.get_include()],
            extra_compile_args=['-Wextra'],
            sources=[pjoin('src', 'datacube_ext.c')]),

        Extension(
            'autopick_ext',
            include_dirs=[numpy.get_include()],
            extra_compile_args=['-Wextra'],
            sources=[pjoin('src', 'autopick_ext.c')]),

        Extension(
            'gf.store_ext',
            include_dirs=[numpy.get_include()],
            extra_compile_args=['-D_FILE_OFFSET_BITS=64', '-Wextra'] + omp_arg,
            extra_link_args=[] + omp_lib,
            sources=[pjoin('src', 'gf', 'ext', 'store_ext.c')]),

        Extension(
            'parstack_ext',
            include_dirs=[numpy.get_include()],
            extra_compile_args=['-Wextra'] + omp_arg,
            extra_link_args=[] + omp_lib,
            sources=[pjoin('src', 'parstack_ext.c')]),

        Extension(
            'ahfullgreen_ext',
            include_dirs=[numpy.get_include()],
            extra_compile_args=['-Wextra'],
            sources=[pjoin('src', 'ahfullgreen_ext.c')]),

        Extension(
            'orthodrome_ext',
            include_dirs=[numpy.get_include()],
            extra_compile_args=['-Wextra'],
            sources=[pjoin('src', 'orthodrome_ext.c')]),
    ],

    scripts=[
        'apps/snuffler',
        'apps/hamster',
        'apps/cake',
        'apps/fomosto',
        'apps/jackseis',
        'apps/gmtpy-epstopdf',
        'apps/automap'],

    package_data={
        packname: ['data/*.png', 'data/*.html', 'data/earthmodels/*.nd',
                   'data/colortables/*.cpt', 'data/tectonics/*.txt',
                   'data/fomosto_report/gfreport.*']},
)
