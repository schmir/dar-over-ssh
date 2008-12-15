#! /usr/bin/env python

"""
create backups using the dar (http://dar.linux.free.fr/)
command line utility via ssh
"""

import sys
import os
import datetime
import shutil
import binascii
import glob

def get_datestring():
    return datetime.datetime.today().strftime("%Y%m%d%H%M")

def system(cmd):
    sys.stdout.write("running %s\n" % (cmd,))
    
    sys.stdout.flush()
    sys.stderr.flush()
    
    err=os.system(cmd)
    return err
    
class ssh_backup(object):
    def __init__(self,
                 source,
                 name=None,
                 prune=None,
                 dstdir=None,
                 backupdir=os.path.expanduser("~/backup")):


        if not prune:
            prune = []
        elif isinstance(prune, str):
            prune = [x.strip().lstrip("/") for x in prune.split()]
            
        self.prune = prune
        
        if name is None:
            name = source.replace("/", ":")
        self.name = name
            
        host, source = source.split(":", 1)
        
        self.source = source
        self.host = host

        if dstdir is None:
            dstdir = name

        self.dstdir = os.path.join(backupdir, dstdir)
        self.date = get_datestring()
        self.uid = binascii.hexlify(open("/dev/random").read(6))
        
    def run(self):

        reference = None

        full_backups = glob.glob(os.path.join(self.dstdir, "*-full/archive.1.dar"))
        full_backups.sort()
        if full_backups:
            reference = full_backups[-1]
            sys.stdout.write("using reference %s\n"  % reference)
        else:
            sys.stdout.write("no full backups found. will create one.\n")
               
        cmd = 'ssh %s dar -z -Q -c - -R %s' % (self.host, self.source)
        cmd += r" -Z '\*.i' -Z '\*.gz' -Z '\*.tgz' -Z '\*.bz2' -Z '\*.zip' -Z '\*.pack' -Z '\*.i' -Z 'pack\*.pack' -Z '\*.7z' -Z '\*.rz'"

        tmpdir = os.path.join(self.dstdir, 'tmp')
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)

        os.makedirs(tmpdir)

        if reference:
            reference_catalog = os.path.join(os.path.dirname(reference), "catalog.1.dar")
            os.symlink(reference, os.path.join(tmpdir, "reference"))
            remote_ref = '/tmp/catalog-%s' % (self.uid,)
            err = system("scp -q %s %s:%s.1.dar" % (reference_catalog, self.host, remote_ref))
            assert err==0, "could not copy catalog to remote host"
            
            cmd += ' -A %s ' % (remote_ref,)
            
        archive = os.path.join(tmpdir, "archive.1.dar")

        cmd += ' %s ' % (" ".join(['-P%s' % x for x in self.prune]),)
        
        
        cmd += ' >%s ' % (archive,)
        system(cmd)

        if reference:
            cmd = "ssh %s rm %s.1.dar" % (self.host, remote_ref)
            system(cmd)
            
        catalog = os.path.join(tmpdir, "catalog")
        err=system("dar -C %s -A %s" % (catalog, os.path.join(tmpdir, "archive")))
        assert err==0, "could not create catalog"
        
        if reference:
            n = '-partial'
        else:
            n = '-full'

        fn = os.path.join(self.dstdir, self.date+n)
        
        os.rename(tmpdir, fn)
        sys.stdout.write("created backup in %s\n" % fn)
