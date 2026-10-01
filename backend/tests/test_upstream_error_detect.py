"""Self-check: upstream error detection in groq_analyzer JSON parse."""
from src.infrastructure.groq_analyzer import GroqAnalyzer


def test_quota_error_detected():
    q = '[Error] The free quota has been exhausted. To continue accessing the model on a paid basis, please complete your payment information （or disable the "use free tier only" mode in the management console'
    assert GroqAnalyzer._looks_like_upstream_error(q) is True


def test_normal_output_not_flagged():
    assert GroqAnalyzer._looks_like_upstream_error('{"clips": [{"rank": 1}]}') is False
    assert GroqAnalyzer._looks_like_upstream_error("Ini caption video biasa tanpa marker error") is False


if __name__ == "__main__":
    test_quota_error_detected()
    test_normal_output_not_flagged()
    print("ok")
