"""Verify database schema — is_premium column and existing users."""
import sys
sys.path.insert(0, "/Users/macbookairm1/Documents/autocliper-backend-v01/backend")

from src.infrastructure.db_connection import get_dict_connection

conn = get_dict_connection()
cur = conn.cursor()

# Check users table columns
cur.execute("PRAGMA table_info(users)")
columns = {row["name"]: row for row in cur.fetchall()}
print("=== Users Table Columns ===")
for name, info in columns.items():
    print(f"  {name}: type={info['type']}, notnull={info['notnull']}, default={info['dflt_value']}")

has_premium = "is_premium" in columns
print(f"\nis_premium column exists: {has_premium}")

if not has_premium:
    print("\n[MIGRATING] Adding is_premium column...")
    cur.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    print("[DONE] is_premium column added (default=0)")

# Check existing users with premium status
cur.execute("SELECT id, email, full_name, role_id, is_active, is_premium FROM users")
users = cur.fetchall()
print(f"\n=== Existing Users ({len(users)}) ===")
for u in users:
    role_label = "superadmin" if u["role_id"] == 1 else "editor" if u["role_id"] == 2 else "viewer"
    premium_label = "PREMIUM" if u["is_premium"] else "FREE"
    print(f"  [{u['id']}] {u['email']} | {u['full_name']} | {role_label} | {premium_label}")

# Check roles
cur.execute("SELECT id, name FROM roles")
roles = cur.fetchall()
print(f"\n=== Roles ===")
for r in roles:
    print(f"  {r['id']}: {r['name']}")

conn.close()
print("\n[OK] Database schema verified")
