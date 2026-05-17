
import duckdb, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("dej.sync")

LOCAL_DB = "/Volumes/ExternalHardDrive/dej-intelligence-data/dej_intelligence.duckdb"
token = None
with open(".env.local") as f:
    for line in f:
        if "MOTHERDUCK_TOKEN" in line:
            token = line.split("=", 1)[1].strip()
            break

MD_DB = f"md:dej_intelligence?motherduck_token={token}"
con = duckdb.connect(MD_DB)
con.execute(f"ATTACH '{LOCAL_DB}' AS local (READ_ONLY)")

all_cols = con.execute("SELECT column_name FROM information_schema.columns WHERE table_name='transition_scores' AND table_schema='main' ORDER BY ordinal_position").fetchall()
seen = set()
unique_cols = []
for (col,) in all_cols:
    if col not in seen:
        seen.add(col)
        unique_cols.append(col)

log.info(f"Unique columns: {unique_cols}")
col_list = ", ".join(unique_cols)

log.info("Syncing transition_scores...")
con.execute("DELETE FROM transition_scores")
con.execute(f"INSERT INTO transition_scores ({col_list}) SELECT {col_list} FROM local.transition_scores")
count = con.execute("SELECT COUNT(*) FROM transition_scores").fetchone()[0]
log.info(f"transition_scores: {count} rows")

md_f = {r[0]: r[1] for r in con.execute("SELECT tax_year, COUNT(*) FROM filings GROUP BY tax_year").fetchall()}
local_f = {r[0]: r[1] for r in con.execute("SELECT tax_year, COUNT(*) FROM local.filings GROUP BY tax_year").fetchall()}

for year, local_cnt in sorted(local_f.items()):
    md_cnt = md_f.get(year, 0)
    if md_cnt < local_cnt:
        log.info(f"Filings {year}: MD={md_cnt} local={local_cnt} syncing...")
        con.execute(f"DELETE FROM filings WHERE tax_year = {year}")
        con.execute(f"INSERT INTO filings SELECT * FROM local.filings WHERE tax_year = {year}")
        log.info(f"Filings {year}: done")

log.info("Final MotherDuck counts:")
for table in ["officers", "filings", "transition_scores", "organizations"]:
    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    log.info(f"  {table}: {count}")

con.close()
log.info("Done.")
