"""Export small mart snapshots from the taxi warehouse as copilot fixtures."""
import duckdb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT.parent / "nyc-taxi-semantic-layer" / "data" / "warehouse.duckdb"
DST = ROOT / "data" / "fixtures"
DST.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(SRC), read_only=True)
tables = con.execute(
    "select table_name from information_schema.tables where table_schema='marts'"
).df()["table_name"].tolist()
print("marts tables:", tables)

for t in tables:
    # reservoir sample so fixtures span the whole quarter, not just January
    df = con.execute(
        f"select * from marts.{t} using sample 3000 rows (reservoir)"
    ).df()
    df.to_csv(DST / f"{t}.csv", index=False)
    print(f"{t}: {len(df)} rows -> fixtures")
