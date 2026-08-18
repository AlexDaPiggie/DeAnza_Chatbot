from core.schemas import ChunkMetaData, Chunk
meta = ChunkMetaData(
    source_type="course", 
    code = "CIS 22A",
    title = "Intro to C++",
)
chunk = Chunk (
    source_type="course",
    source_url="https://deanza.edu",
    doc_id="cis-22a",
    title="CIS 22A",
    chunk_text="Intro to programming in C++...",
    metadata = meta,
)
def test_verify_chunkdata():
    assert chunk.metadata.code == "CIS 22A"
    assert chunk.doc_id == "cis-22a"
    print ('Schemas verfied')