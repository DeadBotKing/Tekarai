import pyodbc
CONN_STR = r"DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLEXPRESS;DATABASE=TekaraiLive;Trusted_Connection=yes;"
conn = pyodbc.connect(CONN_STR, autocommit=True)
cur = conn.cursor()
def q(sql, params=()):
    try:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        print(f"\n--- {sql[:140]} ---")
        print("cols:", cols)
        for r in rows[:100]:
            print(r)
        print(f"total {len(rows)} rows")
    except Exception as e:
        print(f"\n[ERR] {sql[:120]} -> {e}")

q("SELECT name FROM sys.tables ORDER BY name")
q("SELECT TOP 50 * FROM [Role]")
q("SELECT TOP 100 * FROM [Permission] ORDER BY code")
q("SELECT TOP 100 * FROM [RolePermission]")
q("SELECT TOP 20 * FROM [UserRole]")
q("SELECT id, username, displayName, status FROM [User] WHERE deletedAt IS NULL ORDER BY username")
try:
    q("SELECT id, code, name FROM [OrganizationDepartment]")
except Exception as e:
    print(e)
try:
    q("SELECT id, code, name FROM [OrganizationPosition]")
except Exception as e:
    print(e)
try:
    q("SELECT * FROM [OrganizationAssignment]")
except Exception as e:
    print(e)
