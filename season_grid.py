"""Pre-compute the model runs the Summer season page needs, and save them to season_grid.csv.

Run once (takes about 10 minutes):  python season_grid.py
Re-run it after changing the weather in season.py or the model in coolhead_model.py.
"""
import sys
import time
from multiprocessing import Pool

import pandas as pd

import season


def main(workers=None):
    jobs = list(season.grid_jobs())
    t0 = time.time()
    with Pool(workers) as pool:
        rows = []
        for i, row in enumerate(pool.imap_unordered(season.run_job, jobs, chunksize=4), 1):
            rows.append(row)
            if i % 50 == 0 or i == len(jobs):
                print(f"{i}/{len(jobs)} runs, {time.time() - t0:.0f} s", flush=True)
    df = pd.DataFrame(rows).sort_values(["city", "month", "case"]).reset_index(drop=True)
    df.round(4).to_csv(season.GRID_FILE, index=False)
    print("saved", season.GRID_FILE, len(df), "rows")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
