from core.retrieval import hybrid_search
def test_retrieval_simple():
    results = hybrid_search("Prerequisites for CIS 22A", top_k=3)
    assert results[0].meta.get("code") == "CIS 22A"
    print ("Hybrid search test passed")