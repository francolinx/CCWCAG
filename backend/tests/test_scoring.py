from backend.app.services.scoring import compute_score


def _page(pid, prio=0):
    return {"id": pid, "priority": prio, "url": f"https://x/{pid}"}


def _f(rule, page_id, severity="serious"):
    return {
        "rule_id": rule,
        "page_id": page_id,
        "severity": severity,
        "wcag_refs": [{"criterion": "1.1.1"}],
        "annotated_screenshot_path": "x.png",
    }


def test_perfect_score_when_no_findings():
    score, grade, stats = compute_score([], [_page("p1", 100), _page("p2")])
    assert score == 100.0
    assert grade == "A"


def test_score_penalises_severity():
    pages = [_page("p1", 100)]
    score, grade, _ = compute_score(
        [_f("image-alt", "p1", "critical"), _f("image-alt", "p1", "minor")], pages
    )
    assert score < 100
    assert grade in {"A", "B", "C", "D", "F"}


def test_homepage_weight_higher_than_inner():
    # Same finding on homepage is penalised more than on an inner page.
    s_home, _, _ = compute_score([_f("image-alt", "p1", "critical")], [_page("p1", 100)])
    s_inner, _, _ = compute_score([_f("image-alt", "p1", "critical")], [_page("p1", 20)])
    assert s_home < s_inner


def test_systemic_rule_detected():
    pages = [_page(f"p{i}") for i in range(4)]
    findings = [_f("image-alt", p["id"]) for p in pages]
    _, _, stats = compute_score(findings, pages)
    assert "image-alt" in stats["systemic_rules"]


def test_grade_bands():
    # Force a low score with many criticals on homepage.
    pages = [_page("p1", 100)]
    findings = [_f("r" + str(i), "p1", "critical") for i in range(8)]
    score, grade, _ = compute_score(findings, pages)
    assert grade == "F" or score <= 60
