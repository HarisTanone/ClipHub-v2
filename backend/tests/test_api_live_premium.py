"""Live API Test — Premium/Free user flow verification.

Tests the actual running server at localhost:8000.
Covers:
1. Login as superadmin → verify is_premium/pipeline in /auth/me
2. Login as regular user → verify FREE status
3. Superadmin sets user to premium → verify change
4. Verify /features/my reflects premium status
5. Superadmin sets user back to free → verify
6. Test invalid scenarios (non-admin toggle, missing user)
"""
import sys
import requests

BASE = "http://localhost:8000/api"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def login(email: str, password: str) -> str:
    """Login and return access token."""
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        print(f"  [LOGIN FAIL] {email}: {r.status_code} {r.text[:100]}")
        return ""
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def get_me(token: str) -> dict:
    r = requests.get(f"{BASE}/auth/me", headers=auth_headers(token))
    return r.json().get("data", {})


passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {detail}")


# ─── Test Execution ───────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("  LIVE API TEST — Premium/Free User Flow")
print("=" * 60)

# ─── 1. Login as superadmin ───────────────────────────────────────────────────
print("\n── 1. Superadmin Login & Status ──")
admin_token = login("admin@autocliper.com", "Admin@2024!Secure")
check("Superadmin login success", bool(admin_token))

if admin_token:
    me = get_me(admin_token)
    check("Superadmin is_superadmin=True", me.get("is_superadmin") is True)
    check("Superadmin is_premium=True", me.get("is_premium") is True)
    check("Superadmin pipeline=v1", me.get("pipeline") == "v1")
    check("Superadmin features=all", len(me.get("features", [])) == 5, f"got {me.get('features')}")

# ─── 2. Create test user (or login existing) ─────────────────────────────────
print("\n── 2. Regular User (Free) ──")

# Try to create a test user
if admin_token:
    create_r = requests.post(f"{BASE}/auth/users", json={
        "email": "testfree@test.com",
        "password": "TestFree123!",
        "full_name": "Test Free User",
        "role_id": 2,
    }, headers=auth_headers(admin_token))
    if create_r.status_code == 201:
        print("  Created testfree@test.com")
    elif create_r.status_code == 409:
        print("  testfree@test.com already exists")

free_token = login("testfree@test.com", "TestFree123!")
check("Free user login success", bool(free_token))

if free_token:
    me = get_me(free_token)
    check("Free user is_premium=False", me.get("is_premium") is False)
    check("Free user pipeline=v2", me.get("pipeline") == "v2")
    check("Free user features=[]", me.get("features") == [], f"got {me.get('features')}")

# ─── 3. Check /features/my for free user ─────────────────────────────────────
print("\n── 3. GET /features/my ──")
if free_token:
    r = requests.get(f"{BASE}/features/my", headers=auth_headers(free_token))
    data = r.json()
    check("/features/my returns is_premium=False", data.get("is_premium") is False)
    check("/features/my returns pipeline=v2", data.get("pipeline") == "v2")
    check("/features/my returns features=[]", data.get("features") == [])

if admin_token:
    r = requests.get(f"{BASE}/features/my", headers=auth_headers(admin_token))
    data = r.json()
    check("/features/my superadmin is_premium=True", data.get("is_premium") is True)
    check("/features/my superadmin has all features", len(data.get("features", [])) == 5)

# ─── 4. Superadmin sets user to Premium ───────────────────────────────────────
print("\n── 4. Set User → Premium ──")
if admin_token and free_token:
    # Get user ID
    me_free = get_me(free_token)
    free_user_id = me_free.get("id")
    
    r = requests.post(f"{BASE}/features/set-premium", json={
        "user_id": free_user_id,
        "is_premium": True,
    }, headers=auth_headers(admin_token))
    data = r.json()
    check("set-premium returns success", data.get("success") is True)
    check("set-premium returns pipeline=v1", data.get("data", {}).get("pipeline") == "v1")
    check("set-premium returns all features", len(data.get("data", {}).get("features", [])) == 5)
    
    # Verify user now sees premium
    me_after = get_me(free_token)
    check("User now is_premium=True", me_after.get("is_premium") is True)
    check("User now pipeline=v1", me_after.get("pipeline") == "v1")
    check("User now has all features", len(me_after.get("features", [])) == 5)

# ─── 5. Set user back to Free ─────────────────────────────────────────────────
print("\n── 5. Set User → Free ──")
if admin_token and free_token:
    r = requests.post(f"{BASE}/features/set-premium", json={
        "user_id": free_user_id,
        "is_premium": False,
    }, headers=auth_headers(admin_token))
    data = r.json()
    check("set-premium(false) returns success", data.get("success") is True)
    check("set-premium(false) returns pipeline=v2", data.get("data", {}).get("pipeline") == "v2")
    check("set-premium(false) returns features=[]", data.get("data", {}).get("features") == [])
    
    # Verify user reverted
    me_reverted = get_me(free_token)
    check("User reverted is_premium=False", me_reverted.get("is_premium") is False)
    check("User reverted pipeline=v2", me_reverted.get("pipeline") == "v2")
    check("User reverted features=[]", me_reverted.get("features") == [])

# ─── 6. Error Scenarios ───────────────────────────────────────────────────────
print("\n── 6. Error Scenarios ──")

# Non-admin cannot set premium
if free_token:
    r = requests.post(f"{BASE}/features/set-premium", json={
        "user_id": 1,
        "is_premium": True,
    }, headers=auth_headers(free_token))
    check("Non-admin cannot set-premium (403)", r.status_code == 403)

# Invalid user ID
if admin_token:
    r = requests.post(f"{BASE}/features/set-premium", json={
        "user_id": 99999,
        "is_premium": True,
    }, headers=auth_headers(admin_token))
    check("Invalid user_id returns 404", r.status_code == 404)

# No auth
r = requests.get(f"{BASE}/features/my")
check("No auth returns 401/403", r.status_code in (401, 403))

# ─── 7. GET /features/user/{id} (superadmin view) ────────────────────────────
print("\n── 7. GET /features/user/{id} ──")
if admin_token and free_user_id:
    r = requests.get(f"{BASE}/features/user/{free_user_id}", headers=auth_headers(admin_token))
    data = r.json()
    check("/features/user returns success", data.get("success") is True)
    check("/features/user shows is_premium field", "is_premium" in data.get("data", {}))

# ─── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"  RESULTS: {passed} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("  ALL LIVE API TESTS PASSED")
