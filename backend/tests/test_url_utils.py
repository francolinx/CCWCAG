from backend.app.utils.url import (
    canonical_domain,
    normalize_url,
    same_site,
    score_candidate,
)


def test_canonical_domain_strips_www():
    assert canonical_domain("https://www.Example.com/foo") == "example.com"


def test_normalize_url_drops_fragments_and_non_http():
    assert normalize_url("https://x.com/", "javascript:void(0)") is None
    assert normalize_url("https://x.com/", "#top") is None
    assert normalize_url("https://x.com/", "mailto:a@b.com") is None
    assert normalize_url("https://x.com/", "/foo#bar") == "https://x.com/foo"


def test_same_site_requires_same_canonical_domain():
    assert same_site("https://www.x.com/a", "https://x.com/b")
    assert not same_site("https://x.com/a", "https://y.com/b")


def test_score_candidate_prefers_homepage():
    assert score_candidate("https://x.com/") > score_candidate("https://x.com/deep/nested/path/x")


def test_score_candidate_rewards_important_keywords():
    assert score_candidate("https://x.com/checkout") > score_candidate("https://x.com/blog/post")
