from scrapers.terms import get_active_catalog_term, get_current_quarter
term = get_active_catalog_term()
quarter = get_current_quarter()
def test_find_current_term():
    print (f"Detected Term: {term}, Quarter: {quarter}")
    assert "-" in term and len(term) == 9
