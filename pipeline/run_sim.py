"""Parallel, checkpointed simulation of every (topology x dataset). Safe to interrupt and re-run."""
import sys, time
from multiprocessing import Pool
import vgrid

CHUNK_DAYS = 30

def main(topos, datasets, workers=18):
    jobs = []
    for d in datasets:
        n_days = len(vgrid.scenarios(d))
        print(f"dataset '{d}': {n_days} fully-observed real days")
        for t in topos:
            for c, lo in enumerate(range(0, n_days, CHUNK_DAYS)):
                jobs.append((t, d, c, lo, min(lo + CHUNK_DAYS, n_days)))
    t0 = time.time()
    done = 0
    with Pool(workers) as pool:
        for path, dt in pool.imap_unordered(vgrid.sim_chunk, jobs):
            done += 1
            if dt:
                print(f"[{done}/{len(jobs)}] {path.split(chr(92))[-1]} {dt:.0f}s (elapsed {time.time()-t0:.0f}s)", flush=True)
    print(f"all chunks present. total {time.time()-t0:.0f}s")

if __name__ == "__main__":
    topos = sys.argv[1].split(",") if len(sys.argv) > 1 else vgrid.TOPOLOGIES
    datasets = sys.argv[2].split(",") if len(sys.argv) > 2 else ["de"]
    main(topos, datasets, int(sys.argv[3]) if len(sys.argv) > 3 else 18)
