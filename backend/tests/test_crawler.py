from app.services.crawler import CompanyCrawler


def test_canonical_host_ignores_www_prefix() -> None:
    crawler = object.__new__(CompanyCrawler)

    assert crawler._canonical_host("https://www.darbouwadvies.nl/") == "darbouwadvies.nl"
    assert crawler._canonical_host("https://darbouwadvies.nl/over-ons/") == "darbouwadvies.nl"


def test_normalize_url_removes_fragments_but_keeps_path_trailing_slash() -> None:
    crawler = object.__new__(CompanyCrawler)

    assert crawler._normalize_url("https://darbouwadvies.nl/contact/#content") == "https://darbouwadvies.nl/contact/"
    assert crawler._normalize_url("https://darbouwadvies.nl/") == "https://darbouwadvies.nl"
