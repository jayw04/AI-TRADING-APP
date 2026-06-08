import sqlite3, sys

db = sys.argv[1]
con = sqlite3.connect(db)
cur = con.cursor()

print("=== TABLES ===")
for (name,) in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
):
    print(" ", name)

print("\n=== TRIGGERS (expect NONE on audit_log pre-P5) ===")
for (name, tbl) in cur.execute(
    "SELECT name, tbl_name FROM sqlite_master WHERE type='trigger' ORDER BY name;"
):
    print(f"  {name}  (on {tbl})")

for tbl in ("accounts", "strategies", "users", "risk_limits", "audit_log", "orders", "backtests", "fills"):
    print(f"\n=== {tbl} columns ===")
    try:
        for cid, col, ctype, notnull, dflt, pk in cur.execute(f"PRAGMA table_info({tbl});"):
            print(f"  {col:32} {ctype:14} notnull={notnull} pk={pk}")
    except sqlite3.OperationalError as e:
        print(f"  !! {e}")

con.close()
