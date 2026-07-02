import time

from awareness.state_cache import StateCache


def test_state_cache_ocr_result_roundtrip():
    cache = StateCache()
    before = time.time()
    cache.update_ocr_result("hello world", confidence=0.9)
    assert cache.get_ocr_text() == "hello world"
    assert cache.get_ocr_error() is None
    assert cache.get_ocr_confidence() == 0.9
    ts = cache.ocr_last_updated()
    assert ts is not None
    assert ts >= before


def test_state_cache_ocr_error_roundtrip():
    cache = StateCache()
    cache.update_ocr_error("failed", confidence=None)
    assert cache.get_ocr_text() is None
    assert cache.get_ocr_error() == "failed"
    assert cache.ocr_last_updated() is not None
