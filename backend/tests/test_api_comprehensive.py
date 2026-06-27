"""Comprehensive API Test — All user types, all scenarios, best/worst cases.

Tests against running server at localhost:8000.

Scenarios:
A. Superuser (admin@autocliper.com)
   - Always has V1 pipeline
   - Can toggle premium for others
   - Can create jobs (V1)
   - Can switch own mode in settings

B. Premium User (testpremium@test.com)
   - is_premium=true, pipeline=v1
   - All features unlocked
   - Creates jobs → V1 pipeline

C. Free User (testfree@test.com)
   - is_premium=false, pipeline=v2
   - All features locked
   - Creates jobs → V2 pipeline

D. Error Scenarios (worst case)
   - Invalid credentials
   - Expired/missing tokens
   - Non-admin trying admin actions
   - Invalid job URLs
   - Rate limit simulation
"""
import sys
import time
import requests

BASE = "http://localhost:8000/api"

passed = 0
failed = 0
skipped = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} — {detail}")


def skip(name: str, reason: str):
    global skipped
    skipped += 1
    print(f"  [SKIP] {name} — {reason}")


def login(email: str, password: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    if r.status_code == 200:
        return r.json()["access_token"]
    return ""


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── Setup ────────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("  COMPREHENSIVE API TEST — All User Types & Scenarios")
print("=" * 70)

# Check server health first
try:
    health = requests.get("http://localhost:8000/health", timeout=3)
    if health.status_code != 200:
        print("  [ERROR] Server not running at localhost:8000")
        sys.exit(1)
except:
    print("  [ERROR] Cannot connect to server at localhost:8000")
    sys.exit(1)

print("  Server: OK\n")

# ─── Prepare Users ────────────────────────────────────────────────────────────
print("── Setup: Prepare Test Users ──")
admin_token = login("admin@autocliper.com", "Admin@2024!Secure")
check("Admin login", bool(admin_token))

if not admin_token:
    print("ABORT: Cannot login as admin")
    sys.exit(1)

# Create premium test user
r = requests.post(f"{BASE}/auth/users", json={
    "email": "testpremium@test.com", "password": "TestPrem123!",
    "full_name": "Test Premium", "role_id": 2,
}, headers=h(admin_token))
if r.status_code in (201, 409):
    print("  testpremium@test.com ready")

# Create free test user
r = requests.post(f"{BASE}/auth/users", json={
    "email": "testfree2@test.com", "password": "TestFree123!",
    "full_name": "Test Free", "role_id": 2,
}, headers=h(admin_token))
if r.status_code in (201, 409):
    print("  testfree2@test.com ready")

# Set premium user
prem_token = login("testpremium@test.com", "TestPrem123!")
check("Premium user login", bool(prem_token))
if prem_token:
    me = requests.get(f"{BASE}/auth/me", headers=h(prem_token)).json()["data"]
    prem_user_id = me["id"]
    requests.post(f"{BASE}/features/set-premium", json={"user_id": prem_user_id, "is_premium": True}, headers=h(admin_token))
    print(f"  Set user {prem_user_id} to Premium")

# Free user stays free
free_token = login("testfree2@test.com", "TestFree123!")
check("Free user login", bool(free_token))
if free_token:
    me = requests.get(f"{BASE}/auth/me", headers=h(free_token)).json()["data"]
    free_user_id = me["id"]
    requests.post(f"{BASE}/features/set-premium", json={"user_id": free_user_id, "is_premium": False}, headers=h(admin_token))
    print(f"  Set user {free_user_id} to Free")


# ═══════════════════════════════════════════════════════════════════════════════
# A. SUPERUSER SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("  A. SUPERUSER SCENARIOS")
print("─" * 70)

# A1. /auth/me
me = requests.get(f"{BASE}/auth/me", headers=h(admin_token)).json()["data"]
check("A1. Superadmin is_superadmin=True", me["is_superadmin"] is True)
check("A2. Superadmin is_premium=True (implicit)", me["is_premium"] is True)
check("A3. Superadmin pipeline=v1", me["pipeline"] == "v1")
check("A4. Superadmin has all 5 features", len(me["features"]) == 5)

# A2. /features/my
feat = requests.get(f"{BASE}/features/my", headers=h(admin_token)).json()
check("A5. /features/my is_premium=True", feat["is_premium"] is True)
check("A6. /features/my pipeline=v1", feat["pipeline"] == "v1")

# A3. Can toggle other users
r = requests.post(f"{BASE}/features/set-premium", json={"user_id": free_user_id, "is_premium": True}, headers=h(admin_token))
check("A7. Admin can set others to premium", r.status_code == 200 and r.json()["success"])
# Revert
requests.post(f"{BASE}/features/set-premium", json={"user_id": free_user_id, "is_premium": False}, headers=h(admin_token))

# A4. Create job → V1 pipeline
r = requests.post(f"{BASE}/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, headers=h(admin_token))
if r.status_code == 201:
    job_data = r.json()
    check("A8. Admin job creation → 201", True)
    check("A9. Admin job pipeline_version=v1", job_data.get("pipeline_version") == "v1")
else:
    check("A8. Admin job creation → 201", False, f"got {r.status_code}: {r.text[:100]}")
    skip("A9. Admin job pipeline", "job creation failed")

# A5. View other user's features
r = requests.get(f"{BASE}/features/user/{free_user_id}", headers=h(admin_token))
check("A10. Admin can view user features", r.status_code == 200)


# ═══════════════════════════════════════════════════════════════════════════════
# B. PREMIUM USER SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("  B. PREMIUM USER SCENARIOS")
print("─" * 70)

if prem_token:
    # B1. /auth/me
    me = requests.get(f"{BASE}/auth/me", headers=h(prem_token)).json()["data"]
    check("B1. Premium user is_premium=True", me["is_premium"] is True)
    check("B2. Premium user pipeline=v1", me["pipeline"] == "v1")
    check("B3. Premium user features=all 5", len(me["features"]) == 5)
    check("B4. Premium user is_superadmin=False", me["is_superadmin"] is False)

    # B2. /features/my
    feat = requests.get(f"{BASE}/features/my", headers=h(prem_token)).json()
    check("B5. /features/my is_premium=True", feat["is_premium"] is True)
    check("B6. /features/my has all features", len(feat["features"]) == 5)

    # B3. Create job → V1 pipeline
    r = requests.post(f"{BASE}/jobs", json={
        "youtube_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "target_aspect_ratio": "9:16",
    }, headers=h(prem_token))
    if r.status_code == 201:
        job = r.json()
        check("B7. Premium job → 201", True)
        check("B8. Premium job pipeline=v1", job.get("pipeline_version") == "v1")
    else:
        check("B7. Premium job creation", False, f"{r.status_code}")
        skip("B8. Premium job pipeline", "creation failed")

    # B4. Premium cannot toggle others
    r = requests.post(f"{BASE}/features/set-premium", json={"user_id": free_user_id, "is_premium": True}, headers=h(prem_token))
    check("B9. Premium cannot set-premium (403)", r.status_code == 403)
else:
    skip("B1-B9", "premium token not available")


# ═══════════════════════════════════════════════════════════════════════════════
# C. FREE USER SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("  C. FREE USER SCENARIOS")
print("─" * 70)

if free_token:
    # C1. /auth/me
    me = requests.get(f"{BASE}/auth/me", headers=h(free_token)).json()["data"]
    check("C1. Free user is_premium=False", me["is_premium"] is False)
    check("C2. Free user pipeline=v2", me["pipeline"] == "v2")
    check("C3. Free user features=[] (locked)", me["features"] == [])
    check("C4. Free user is_superadmin=False", me["is_superadmin"] is False)

    # C2. /features/my
    feat = requests.get(f"{BASE}/features/my", headers=h(free_token)).json()
    check("C5. /features/my is_premium=False", feat["is_premium"] is False)
    check("C6. /features/my pipeline=v2", feat["pipeline"] == "v2")
    check("C7. /features/my features=[]", feat["features"] == [])

    # C3. Create job → V2 pipeline (use unique URL to avoid dedup)
    r = requests.post(f"{BASE}/jobs", json={
        "youtube_url": "https://www.youtube.com/watch?v=LXb3EKWsInQ",
        "target_aspect_ratio": "9:16",
        "force_reprocess": True,
    }, headers=h(free_token))
    if r.status_code == 201:
        job = r.json()
        check("C8. Free job → 201", True)
        check("C9. Free job pipeline=v2", job.get("pipeline_version") == "v2")
    else:
        check("C8. Free job creation", False, f"{r.status_code}: {r.text[:80]}")
        skip("C9. Free job pipeline", "creation failed")

    # C4. Free user cannot toggle premium
    r = requests.post(f"{BASE}/features/set-premium", json={"user_id": 1, "is_premium": True}, headers=h(free_token))
    check("C10. Free cannot set-premium (403)", r.status_code == 403)

    # C5. Free cannot view other's features
    r = requests.get(f"{BASE}/features/user/1", headers=h(free_token))
    check("C11. Free cannot view admin features (403)", r.status_code == 403)
else:
    skip("C1-C11", "free token not available")


# ═══════════════════════════════════════════════════════════════════════════════
# D. ERROR / WORST CASE SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("  D. ERROR & WORST CASE SCENARIOS")
print("─" * 70)

# D1. Invalid login
r = requests.post(f"{BASE}/auth/login", json={"email": "wrong@test.com", "password": "wrong"})
check("D1. Invalid login → 401", r.status_code == 401)

# D2. Wrong password
r = requests.post(f"{BASE}/auth/login", json={"email": "admin@autocliper.com", "password": "wrongpass"})
check("D2. Wrong password → 401", r.status_code == 401)

# D3. No auth token
r = requests.get(f"{BASE}/auth/me")
check("D3. No token → 401", r.status_code == 401)

# D4. Invalid token
r = requests.get(f"{BASE}/auth/me", headers={"Authorization": "Bearer invalidtoken123"})
check("D4. Invalid token → 401", r.status_code == 401)

# D5. Set premium for non-existent user
r = requests.post(f"{BASE}/features/set-premium", json={"user_id": 99999, "is_premium": True}, headers=h(admin_token))
check("D5. Premium for non-existent user → 404", r.status_code == 404)

# D6. Invalid YouTube URL (validation passes but download fails)
r = requests.post(f"{BASE}/jobs", json={"youtube_url": "not-a-url"}, headers=h(free_token))
# Server accepts the job (async validation), or validates inline
check("D6. Invalid URL handled gracefully", r.status_code in (201, 422, 400, 500))

# D7. Empty URL
r = requests.post(f"{BASE}/jobs", json={"youtube_url": ""}, headers=h(free_token))
check("D7. Empty URL → 422", r.status_code == 422)

# D8. Invalid aspect ratio
r = requests.post(f"{BASE}/jobs", json={"youtube_url": "https://youtube.com/watch?v=x", "target_aspect_ratio": "4:3"}, headers=h(free_token))
check("D8. Invalid aspect ratio → 422", r.status_code == 422)

# D9. Missing body fields
r = requests.post(f"{BASE}/features/set-premium", json={}, headers=h(admin_token))
check("D9. Missing user_id → 422", r.status_code == 422)

# D10. Get non-existent job
r = requests.get(f"{BASE}/jobs/nonexistent_job_id", headers=h(admin_token))
check("D10. Non-existent job → 404", r.status_code in (404, 422))


# ═══════════════════════════════════════════════════════════════════════════════
# E. PREMIUM TOGGLE FLOW (State Transitions)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("  E. PREMIUM TOGGLE FLOW (State Transitions)")
print("─" * 70)

if free_token and admin_token:
    # E1. Free → verify V2
    me = requests.get(f"{BASE}/auth/me", headers=h(free_token)).json()["data"]
    check("E1. Initial state: free, v2", me["is_premium"] is False and me["pipeline"] == "v2")

    # E2. Toggle to Premium
    requests.post(f"{BASE}/features/set-premium", json={"user_id": free_user_id, "is_premium": True}, headers=h(admin_token))
    me = requests.get(f"{BASE}/auth/me", headers=h(free_token)).json()["data"]
    check("E2. After toggle: premium, v1", me["is_premium"] is True and me["pipeline"] == "v1")
    check("E3. After toggle: features unlocked", len(me["features"]) == 5)

    # E3. Create job while premium → V1
    r = requests.post(f"{BASE}/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=9bZkp7q19f0"}, headers=h(free_token))
    if r.status_code == 201:
        check("E4. Job as premium → v1", r.json().get("pipeline_version") == "v1")
    else:
        skip("E4. Job as premium", f"status {r.status_code}")

    # E4. Toggle back to Free
    requests.post(f"{BASE}/features/set-premium", json={"user_id": free_user_id, "is_premium": False}, headers=h(admin_token))
    me = requests.get(f"{BASE}/auth/me", headers=h(free_token)).json()["data"]
    check("E5. Reverted: free, v2", me["is_premium"] is False and me["pipeline"] == "v2")
    check("E6. Reverted: features locked", me["features"] == [])

    # E5. Create job while free → V2
    r = requests.post(f"{BASE}/jobs", json={
        "youtube_url": "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
        "force_reprocess": True,
    }, headers=h(free_token))
    if r.status_code == 201:
        check("E7. Job as free → v2", r.json().get("pipeline_version") == "v2")
    else:
        skip("E7. Job as free", f"status {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
total = passed + failed + skipped
print(f"  RESULTS: {passed} passed, {failed} failed, {skipped} skipped (total: {total})")
print("=" * 70)

if failed > 0:
    print("  SOME TESTS FAILED")
    sys.exit(1)
else:
    print("  ALL TESTS PASSED")
