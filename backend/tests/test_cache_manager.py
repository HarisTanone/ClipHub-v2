import os
import pytest
from src.infrastructure.cache_manager import CacheManager

def test_cache_manager_invalidate(tmp_path, monkeypatch):
    cache = CacheManager()
    cache._cache_dir = str(tmp_path)
    
    vid = "testvid1234"
    vpath = cache._video_path(vid)
    tpath = cache._transcript_path(vid)
    a1path = cache._analysis_path(vid, "v1")
    a2path = cache._analysis_path(vid, "v2")
    
    for p in [vpath, tpath, a1path, a2path]:
        with open(p, "w") as f:
            f.write("test")
        assert os.path.exists(p)
        
    cache.invalidate(vid)
    
    for p in [vpath, tpath, a1path, a2path]:
        assert not os.path.exists(p)
