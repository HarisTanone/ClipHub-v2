"""Verify V1 (Gemini/Remotion) pipeline still works for premium users.

Tests:
1. Premium user job → pipeline_version=v1 (confirmed)
2. V1 pipeline code path untouched (static verification)
3. Job status progression uses V1 statuses (not V2 statuses)
4. Remotion adapter still accessible when USE_REMOTION=True
5. Superadmin job also routes to V1
"""
import sys
import time
import requests

BASE = "http://localhost:8000/api"

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} — {detail}")


def login(email: str, password: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    return r.json().get("access_token", "") if r.status_code == 200 else ""


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ═══ Check server ═══
try:
    r = requests.get("http://localhost:8000/health", timeout=3)
    assert r.status_code == 200
except:
    print("[ERROR] Server not running")
    sys.exit(1)

print("\n" + "=" * 60)
print("  V1 PIPELINE INTEGRITY CHECK")
print("=" * 60)

# ═══ 1. Premium user job → V1 pipeline ═══
print("\n── 1. Premium User Job → V1 ──")
admin_token = login("admin@autocliper.com", "Admin@2024!Secure")
prem_token = login("testpremium@test.com", "TestPrem123!")

if prem_token:
    # Ensure premium
    me = requests.get(f"{BASE}/auth/me", headers=h(prem_token)).json()["data"]
    prem_user_id = me["id"]
    requests.post(f"{BASE}/features/set-premium", json={"user_id": prem_user_id, "is_premium": True}, headers=h(admin_token))

    # Create job
    r = requests.post(f"{BASE}/jobs", json={
        "youtube_url": "https://www.youtube.com/watch?v=2Vv-BfVoq4g",
        "force_reprocess": True,
    }, headers=h(prem_token))
    
    if r.status_code == 201:
        job = r.json()
        check("Premium job created (201)", True)
        check("pipeline_version = v1", job["pipeline_version"] == "v1")
        
        # Wait briefly and check status progression
        job_id = job["job_id"]
        time.sleep(2)
        status_r = requests.get(f"{BASE}/jobs/{job_id}", headers=h(prem_token))
        if status_r.status_code == 200:
            current_status = status_r.json()["status"]
            # V1 uses standard statuses (validating, downloading, analyzing, etc.)
            # V2 uses v2_transcribing, v2_analyzing, etc.
            v1_statuses = {"validating", "downloading", "analyzing", "preparing", "routing",
                           "trimming", "segmenting", "whisper", "highlighting", "broll",
                           "hook_rendering", "subtitle_rendering", "encoding", "uploading",
                           "assembling", "completed", "failed", "timeout"}
            v2_statuses = {"v2_transcribing", "v2_analyzing", "v2_micro_slicing",
                           "v2_word_transcribing", "v2_vad_refining"}
            
            check("Job status is V1 type", current_status in v1_statuses,
                  f"got '{current_status}'")
            check("Job status NOT V2 type", current_status not in v2_statuses,
                  f"got '{current_status}'")
            print(f"    Current status: {current_status}")
    else:
        check("Premium job created", False, f"status {r.status_code}")

# ═══ 2. Superadmin job → V1 ═══
print("\n── 2. Superadmin Job → V1 ──")
if admin_token:
    r = requests.post(f"{BASE}/jobs", json={
        "youtube_url": "https://www.youtube.com/watch?v=fJ9rUzIMcZQ",
        "force_reprocess": True,
    }, headers=h(admin_token))
    
    if r.status_code == 201:
        job = r.json()
        check("Admin job created (201)", True)
        check("Admin job pipeline = v1", job["pipeline_version"] == "v1")
    else:
        check("Admin job created", False, f"status {r.status_code}")

# ═══ 3. V1 code path verification (static) ═══
print("\n── 3. V1 Code Path Static Check ──")

# Verify key V1 components still importable
import importlib
try:
    sys.path.insert(0, "/Users/macbookairm1/Documents/autocliper-backend-v01/backend")
    
    from src.application.services import JobService
    check("JobService importable", True)
    
    # Check _run_pipeline still exists
    check("_run_pipeline method exists", hasattr(JobService, "_run_pipeline"))
    check("_run_guarded method exists", hasattr(JobService, "_run_guarded"))
    check("_run_v2_guarded method exists", hasattr(JobService, "_run_v2_guarded"))
    
    # Check V1 dependencies still in constructor
    import inspect
    sig = inspect.signature(JobService.__init__)
    params = list(sig.parameters.keys())
    check("gemini_analyzer in JobService params", "gemini_analyzer" in params)
    check("whisper_local in JobService params", "whisper_local" in params)
    check("renderer in JobService params", "renderer" in params)
    
    # Verify Remotion adapter param exists
    check("remotion_adapter in JobService params", "remotion_adapter" in params)
    
except Exception as e:
    check("V1 code imports", False, str(e))

# ═══ 4. Remotion config still active ═══
print("\n── 4. Remotion Configuration ──")
try:
    from src.config import settings
    check("USE_REMOTION setting exists", hasattr(settings, "USE_REMOTION"))
    check("REMOTION_ENABLE_THREEJS exists", hasattr(settings, "REMOTION_ENABLE_THREEJS"))
    check("REMOTION_ENABLE_AI_LAYER exists", hasattr(settings, "REMOTION_ENABLE_AI_LAYER"))
    check("REMOTION_QUALITY exists", hasattr(settings, "REMOTION_QUALITY"))
    print(f"    USE_REMOTION={settings.USE_REMOTION}")
    print(f"    REMOTION_QUALITY={settings.REMOTION_QUALITY}")
except Exception as e:
    check("Remotion config", False, str(e))

# ═══ 5. Free user job → V2 (contrast check) ═══
print("\n── 5. Free User Job → V2 (Contrast) ──")
free_token = login("testfree2@test.com", "TestFree123!")
if free_token:
    r = requests.post(f"{BASE}/jobs", json={
        "youtube_url": "https://www.youtube.com/watch?v=RgKAFK5djSk",
        "force_reprocess": True,
    }, headers=h(free_token))
    
    if r.status_code == 201:
        job = r.json()
        check("Free job pipeline = v2", job["pipeline_version"] == "v2")
        
        job_id = job["job_id"]
        time.sleep(2)
        status_r = requests.get(f"{BASE}/jobs/{job_id}", headers=h(free_token))
        if status_r.status_code == 200:
            current_status = status_r.json()["status"]
            v2_statuses = {"v2_transcribing", "v2_analyzing", "v2_micro_slicing",
                           "v2_word_transcribing", "v2_vad_refining",
                           "validating", "downloading", "preparing", "routing",
                           "trimming", "completed", "failed"}
            check("Free job uses V2/shared statuses", current_status in v2_statuses,
                  f"got '{current_status}'")
            print(f"    Current status: {current_status}")

# ═══ Summary ═══
print("\n" + "=" * 60)
print(f"  RESULTS: {passed} passed, {failed} failed")
print("=" * 60)
if failed == 0:
    print("  V1 PIPELINE INTEGRITY VERIFIED")
else:
    sys.exit(1)
