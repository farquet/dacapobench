#!/usr/bin/env python3
#
# Take the nominal stats of all benchmarks and for each statistic
# find the median result and the rank of a given benchmark among
# the set (so we can see, for example, what the median min heap is,
# and rank the benchmarks according to their min heap).
#
# Author: Steve Blackburn 2023
#
import yaml
import sys
import getopt
import os.path
import math
import statistics

alloc = {}       # allocation stats
bytecode = {}    # bytecode execution stats
minheap = {}     # min heap size stats
perf = {}        # performance stats
gc = {}          # GC stats

nom = {}         # nominal stats
desc = {}        # description of nominal stats

verbose = False

def usage(errno):
    print ('usage: ',sys.argv[0], '-b <path to benchmark>')
    sys.exit(errno)

def load_yml(bmpath):
    global alloc
    global bytecode
    global minheap
    global perf
    global gc

    yml = bmpath + '/stats-alloc.yml'
    if os.path.exists(yml):
        with open(yml, 'r') as y:
            alloc = yaml.load(y, Loader=yaml.Loader)

    yml = bmpath + '/stats-bytecode.yml'
    if os.path.exists(yml):
        with open(yml, 'r') as y:
            bytecode = yaml.load(y, Loader=yaml.Loader)

    yml = bmpath + '/stats-minheap.yml'
    if os.path.exists(yml):
        with open(yml, 'r') as y:
            minheap = yaml.load(y, Loader=yaml.Loader)

    yml = bmpath + '/stats-perf.yml'
    if os.path.exists(yml):
        with open(yml, 'r') as y:
            perf = yaml.load(y, Loader=yaml.Loader)

    yml = bmpath + '/stats-gc.yml'
    if os.path.exists(yml):
        with open(yml, 'r') as y:
            gc = yaml.load(y, Loader=yaml.Loader)

def aggregate(results):
    std = []
    mean = []
    mini = []

    invocations = len(results)
    iterations = len(results[0])

    for itr in range(0, iterations):
        vals = []
        for inv in range(0, invocations):
            vals.append(results[inv][itr])
        std.append(statistics.stdev(vals))
        mean.append(statistics.mean(vals))
        mini.append(min(vals))

    return std, mean, mini;

par_hf = 2000
par_threads = 32

def get_perf_stats():
    global perf

    if perf is None:
        return None, None, None, None, None, None;

    vm_base = 'open-jdk-11.s.cp.gc-G1'
    vm = vm_base+'.t-32'
    vm_one = vm_base+'.taskset-0'

    std = {}
    mean = {}
    mini = {}
    best = None
    best_hf = None
    tightest_hf = 20000
    for hf in perf[vm].keys():
        if perf[vm][hf]:
            if hf < tightest_hf:
                tightest_hf = hf
            std[hf], mean[hf], mini[hf] = aggregate(perf[vm][hf])
            if not best:
                best = min(mean[hf])
                best_hf = hf
            else:
                best = min(best, min(mean[hf]))
                if best == min(mean[hf]):
                    best_hf = hf

    # nominal perf (ms -> sec)
    np = math.ceil(best/1000)

    # heap sensitivity
    tight = min(mean[tightest_hf])
    # hs = int(100*(tight-best)/best)
    # if (hs < 0):
    #     hs = 0

    # warmup (iteration by which the mean is within 2.5% of the best mean)
    tgt = 1.025*best
    wu = 0
    while mean[best_hf][wu] >= tgt:
        wu = wu + 1

    # standard deviation (as a percentage) among invocations at peak performance
    st = int(100*std[best_hf][wu]/mean[best_hf][wu])

    # parallel efficiency (speedup versus ideal speedup)
    xone = perf[vm][par_hf]
    one = perf[vm_one][par_hf]
    std_one, mean_one, mini_one  = aggregate(one)
    pa = int(100*mean_one[wu]/(par_threads*mean[par_hf][wu]))  # perfect scaling -> 100

    return best, np, wu, st, pa, tight;

def objectsizehisto():
    if alloc is None:
        return None;
    histo = {}
    total = 0
    for s in alloc['objects-by-size']:
        total = total + alloc['objects-by-size'][s]
        histo[s] = total
    
    return histo, total;

def get_percentile(histo, total, percentile):
    global alloc

    target = total * percentile

    t = 0
    for s in alloc['objects-by-size']:
        t = t + alloc['objects-by-size'][s]
        if t >= target:
            return s;

    return None; # should not reach here

def get_gc_stats():
    summary = {}
    for hf in gc:
        gctime = 0
        last = 0
        end = 0
        hs = []
        total_hs = 0
        for val in gc[hf]:
            end = val[0]    # we'll use the start time of last GC as the end point
            hs.append(val[1])
            total_hs = total_hs + val[1]
            last = val[2]   # we'll subtract the last pause, since it is after the nominal end
            gctime = gctime + last
        avg_hs = int(total_hs / len(hs))
        hs = sorted(hs)
        med_hs = hs[int(len(hs)/2)]
        totms = int(end * 1000)
        gcms = int(gctime - last)
        summary[hf] = [len(hs), totms, gcms, avg_hs, med_hs]
    return summary

def nominal():
    ap, np, wu, st, pa, tight = get_perf_stats()


    if (not alloc is None):
        histo, total = objectsizehisto()

        nom['AOM'] = int(get_percentile(histo, total, 0.5))
        desc['AOM'] = 'nominal median object size (bytes)'

        nom['AOS'] = int(get_percentile(histo, total, 0.1))
        desc['AOS'] = 'nominal 10-percentile object size (bytes)'

        nom['AOL'] = int(get_percentile(histo, total, 0.9))
        desc['AOL'] = 'nominal 90-percentile object size (bytes)'

        nom['AOA'] = int(alloc['bytes-allocated']/alloc['objects-allocated'])
        desc['AOA'] = 'nominal average object size (bytes)'
        
        nom['ARA'] = int(alloc['bytes-allocated']/(1000*ap))
        desc['ARA'] = 'nominal allocation rate (bytes / usec) ('+str(alloc['bytes-allocated'])+'/'+str(1000*ap)+')'

        nom['GTO'] = int(alloc['bytes-allocated']/(1024*1024*(max(minheap['open-jdk-11.s.cp.gc-G1.t-32.f-10.n-1']))))
        desc['GTO'] = 'nominal memory turnover (total alloc bytes / min heap bytes)'

    hs = int(100*(tight-ap)/ap)
    if (hs < 0):
        hs = 0
    nom['GSS'] = hs
    desc['GSS'] = 'nominal heap size sensitivity (slowdown with tight heap, as a percentage) ('+str(tight)+'/'+str(ap)+')'

    nom['GMH'] = max(minheap['open-jdk-11.s.cp.gc-G1.t-32.f-10.n-1'])
    desc['GMH'] = 'nominal minimum heap size (MB) (with compressed pointers)'

    nom['GMU'] = max(minheap['open-jdk-11.s.up.gc-G1.t-32.f-10.n-1'])
    desc['GMU'] = 'nominal minimum heap size (MB) without compressed pointers'

    one = max(minheap['open-jdk-11.s.cp.gc-G1.t-32.f-10.n-1'])
    ten = max(minheap['open-jdk-11.s.cp.gc-G1.t-32.f-10.n-10'])
    if (not ten is None):
        leakage = int(100*((ten/one)-1))
        if (leakage < 0):
            leakage = 0
        nom['GLK'] = leakage
        desc['GLK'] = 'nominal percent memory leakage (10 iterations / 1 iterations) ('+str(ten)+'/'+str(one)+')'

    nom['PET'] = np
    desc['PET'] = 'nominal execution time (sec)'

    nom['PWU'] = wu
    desc['PWU'] = 'nominal iterations to warm up to within 2.5% of best'

    nom['PPE'] = pa
    desc['PPE'] = 'nominal parallel efficiency (speedup as percentage of ideal speedup for '+str(par_threads)+' threads)'

    nom['PSD'] = st
    desc['PSD'] = 'nominal standard deviation among invocations at peak performance (as percentage of performance)'

    if (not bytecode is None):
        nom['BUB'] = int(bytecode['executed-bytecodes-unique']/1000)
        desc['BUB'] = 'nominal thousands of unique bytecodes executed'

        nom['BEF'] = int(1000*bytecode['executed-bytecodes-p9999']/bytecode['executed-bytecodes'])
        desc['BEF'] = 'nominal execution focus / dominance of hot code'

        nom['BUF'] = int(bytecode['executed-calls-unique']/1000)
        desc['BUF'] = 'nominal thousands of unique function calls'

        nom['BPF'] = int(bytecode['opcodes']['putfield']/(1000*ap))
        desc['BPF'] = 'nominal putfield per usec'
    
        nom['BGF'] = int(bytecode['opcodes']['getfield']/(1000*ap))
        desc['BGF'] = 'nominal getfield per usec'

        nom['BAS'] = int(bytecode['opcodes']['aastore']/(1000*ap))
        desc['BAS'] = 'nominal aastore per usec'

        nom['BAL'] = int(bytecode['opcodes']['aaload']/(1000*ap))
        desc['BAL'] = 'nominal aaload per usec'

    gc_summary = get_gc_stats()
    
    nom['GCC'] = gc_summary[2.0][0]
    desc['GCC'] = 'nominal GC count at 2X heap size (G1)'

    nom['GCP'] = int(100*(gc_summary[2.0][2]/gc_summary[2.0][1]))
    desc['GCP'] = 'nominal percentage of time spent in GC pauses at 2X heap size (G1) ('+str(gc_summary[2.0][2])+'/'+str(gc_summary[2.0][1])+')'

    nom['GCA'] = int(100*(gc_summary[1.0][3]/ten))
    desc['GCA'] = 'nominal average post-GC heap size as percent of min heap, when run at 1X min heap with G1 ('+str(gc_summary[1.0][3])+'/'+str(ten)+')'

    nom['GCM'] = int(100*(gc_summary[1.0][4]/ten))
    desc['GCM'] = 'nominal median post-GC heap size as percent of min heap, when run at 1X min heap with G1 ('+str(gc_summary[1.0][4])+'/'+str(ten)+')'

    print("# [value, mean, benchmark rank, description]")
    for x in sorted(nom):
        print(x+": ["+str(nom[x])+", '"+desc[x]+"']")
  
    # scalability (1 thread v N threads)
    # heap leakage (minheap 1 it v minheap 10 it)
    # heap threads (minheap 1 thread v minheap N threads)
    # heap turnover (alloc / minheap)
    # median object size
    # code intensity (hotspot)
    # 

def main(argv):
    bmpath = None

    try:
        opts, args = getopt.getopt(argv, "hvb:")
    except getopt.GetoptError as e:
        print ('ERROR: Incorrect arguments'.format(e.errno, e.sterror))
        usage(2)
    for opt,arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-v':
            verbose = True
        elif opt == '-b':
            bmpath = arg
    
    if bmpath is None or not os.path.exists(bmpath):
        print ('ERROR: You must specify a valid path to a benchmark')
        usage(2)
    else:
        load_yml(bmpath)
        nominal()

    exit(0)

if __name__ == "__main__":
    main(sys.argv[1:])