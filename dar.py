#! /usr/bin/env python
# Last-changed: 2009-12-28 15:25:05 by ralf

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
    
    def run(self, lifetime=None):
        if lifetime is not None:
            rotate(self.dstdir, lifetime=lifetime)


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

def filename2datetime(fn):
    fn = os.path.basename(fn)
    return datetime.datetime(int(fn[:4]), int(fn[4:6]), int(fn[6:8]), int(fn[8:10]), int(fn[10:12]))
        
def find_archives(path):
    entries = [os.path.join(path, x) for x in os.listdir(path) if x.endswith("-partial") or x.endswith("-full")]
    entries.sort()
    
    lst = []

    for x in entries:
        if x.endswith("-full"):
            lst.append([x])
        else:
            if lst:
                lst[-1].append(x)
                

    return entries, lst

default_lifetime = ((7,2), (30,7), (60,14), (180,60), (360, 120))

def rotate(path, lifetime=None):
    if lifetime is None:
        lifetime = default_lifetime
    
    lifetime = list(lifetime)
    lifetime.sort(reverse=True)
    lifetime.append((-1,0))

    entries, full = find_archives(path)
    if not full:
        return

    partial2full = {}
    for lst in full:
        for x in lst:
            partial2full[x] = lst[0]

    now = datetime.datetime.now()
    
    age = {}
    date = {}

    keep = set()

    def keepentry(e):
        keep.add(e)
        keep.add(partial2full[e])

    keepentry(full[-1][0]) # keep the latest full backup

    # keepentry(full[0][0]) # keep the oldest full backup  XXX does that make sense ???


    for e in entries:
        dt = filename2datetime(e)
        date[e] = dt
        age[e] = (now-dt).days


    def find_min(): 
        """search entry with minimal distance to any entry in keep"""
        
        minimal = (sys.maxint, None)
        for t in todo:
            for k in keep:
                m = (abs((date[t]-date[k]).days), t)
                if m<minimal:
                    minimal = m
        return minimal

    def get_lifetime(age):
        for a, l in lifetime:
            if age>a:
                return l
        assert 0, "guard missing???"

            

    todo = set(entries)-keep
    while todo:
        dist, entry = find_min()
        lt = get_lifetime(age[entry])
        if dist>=lt:
            keepentry(entry)

        todo.remove(entry)


    # finished with marking entries as keep

    def report():
        for lst in full:
            if lst[0] in keep:
                print " ", age[lst[0]], lst[0]
            else:
                print "D", age[lst[0]], lst[0]

            for x in lst[1:]:
                if x in keep:
                    print "    ", age[x], x
                else:
                    print "D   ", age[x], x

    report()



    # delete partial backups before full backups!!
    for e in entries:
        if e.endswith("-partial") and e not in keep:
            # print "rm", e
            shutil.rmtree(e)

    for e in entries:
        if e.endswith("-full") and e not in keep:
            shutil.rmtree(e)
            # print "rm-full", e

