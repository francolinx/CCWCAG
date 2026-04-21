from backend.app.services.secondary_audit import audit_html


def test_detects_image_missing_alt():
    issues = audit_html("<html lang='en'><body><main><img src='x.jpg'></main></body></html>")
    rules = {i.rule_id for i in issues}
    assert "image-alt" in rules


def test_detects_missing_lang():
    issues = audit_html("<html><head><title>t</title></head><body><main>x</main></body></html>")
    assert "html-has-lang" in {i.rule_id for i in issues}


def test_detects_empty_button():
    html = "<html lang='en'><body><main><button></button></main></body></html>"
    assert "button-name" in {i.rule_id for i in audit_html(html)}


def test_detects_empty_link():
    html = "<html lang='en'><body><main><a href='/'></a></main></body></html>"
    assert "link-name" in {i.rule_id for i in audit_html(html)}


def test_detects_missing_title():
    html = "<html lang='en'><body><main>content</main></body></html>"
    assert "document-title" in {i.rule_id for i in audit_html(html)}


def test_detects_missing_main():
    html = "<html lang='en'><head><title>t</title></head><body><p>x</p></body></html>"
    assert "landmark-one-main" in {i.rule_id for i in audit_html(html)}


def test_detects_skipped_heading():
    html = (
        "<html lang='en'><head><title>t</title></head><body><main>"
        "<h1>a</h1><h3>b</h3></main></body></html>"
    )
    assert "heading-order" in {i.rule_id for i in audit_html(html)}


def test_label_found_via_for_attr():
    html = (
        "<html lang='en'><head><title>t</title></head><body><main>"
        "<label for='e'>Email</label><input id='e' type='email'>"
        "</main></body></html>"
    )
    assert "label" not in {i.rule_id for i in audit_html(html)}


def test_good_page_has_no_serious_issues():
    html = """
    <html lang='en'>
      <head><title>Good page</title></head>
      <body>
        <main>
          <h1>Hello</h1>
          <img src='x.jpg' alt='Red backpack'>
          <label for='e'>Email</label>
          <input id='e' type='email'>
          <button>Submit</button>
          <a href='/more'>Learn more</a>
        </main>
      </body>
    </html>
    """
    rules = {i.rule_id for i in audit_html(html)}
    assert "image-alt" not in rules
    assert "label" not in rules
    assert "button-name" not in rules
    assert "link-name" not in rules
