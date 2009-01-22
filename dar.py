#! /usr/bin/env python
# Time-stamp: <2009-01-22 10:55:01 ralf>

"""
create backups using the dar (http://dar.linux.free.fr/)
command line utility via ssh. You'll need a recent version of
dar both on the source and destination systems.
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

def _path_list(path):
    if not path:
        path = []
    elif isinstance(path, str):
        path = [x.strip().lstrip("/") for x in path.split()]
    return path

class ssh_backup(object):
    def __init__(self,
                 source,
                 name=None,
                 prune=None,
                 go_into=None,
                 dstdir=None,
                 backupdir=os.path.expanduser("~/backup")):

        self.prune = _path_list(prune)
        self.go_into = _path_list(go_into)
        
        if name is None:
            name = source.replace("/", ":")
        self.name = name
            
        host, source = source.split(":", 1)
        if not source:
            source = '.'
            
        self.source = source
        self.host = host

        if dstdir is None:
            dstdir = name

        self.dstdir = os.path.join(backupdir, dstdir)
        self.date = get_datestring()
        self.uid = binascii.hexlify(open("/dev/random").read(6))


    def glob(self, pattern):
        return glob.glob(os.path.join(self.dstdir, pattern))

    def filesize(self, name):
        return os.stat(name).st_size
        
    def should_make_full(self, full):
        partial_backups = [x for x in self.glob("*-partial/archive.1.dar") if x>full]
        partial_backups.sort()

        if not partial_backups:
            print "no partial backups"
            return False
        
        size = self.filesize(full)
        all_sizes = [self.filesize(x) for x in partial_backups]
        last_size = all_sizes[-1]
        

        percent = 100.0*last_size / size
        all_percent = 100.0*sum(all_sizes) / size
        
        print "have %d partial backups" % len(partial_backups)
        print "together they use %.1f%% of the size of the last full backup" % (all_percent,)
        print "the last one uses %.1f%% of the size of the last full backup" % (percent,)
        
        if percent>10.0 or len(partial_backups)>90 or all_percent>100.0: # fixme: what are the best values here???
            print "forcing full backup"
            return True

        return False
    
    def run(self):

        reference = None

        full_backups = self.glob("*-full/archive.1.dar")
        full_backups.sort()
        if full_backups:
            reference = full_backups[-1]
            sys.stdout.write("last full backup found in %s\n"  % reference)
            if self.should_make_full(reference):
                reference = None
        else:
            sys.stdout.write("no full backups found. will create one.\n")
            
        cmd = 'ssh %s dar -z -Q -c - -R %s' % (self.host, self.source)
        cmd += r" -Z '\*.i' -Z '\*.gz' -Z '\*.tgz' -Z '\*.bz2' -Z '\*.zip' -Z '\*.pack' -Z '\*.7z' -Z '\*.rz'"

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
        cmd += ' %s ' % (" ".join(['-g%s' % x for x in self.go_into]),)
        
        cmd += ' >%s ' % (archive,)
        system(cmd)

        if reference:
            cmd = "ssh %s rm %s.1.dar" % (self.host, remote_ref)
            system(cmd)
            
        catalog = os.path.join(tmpdir, "catalog")
        err=system("dar -Q -C %s -A %s" % (catalog, os.path.join(tmpdir, "archive")))
        assert err==0, "could not create catalog"
        
        if reference:
            n = '-partial'
        else:
            n = '-full'

        fn = os.path.join(self.dstdir, self.date+n)
        
        os.rename(tmpdir, fn)
        sys.stdout.write("created backup in %s\n" % fn)
