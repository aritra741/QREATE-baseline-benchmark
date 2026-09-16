from quwarts.experiments.extract_util import field_terms, longer_text, schema_context


def test_field_terms_drop_stopwords_and_keep_phrase():
    terms = field_terms("uses_knowledge_graph")
    assert "knowledge" in terms
    assert "graph" in terms
    assert "knowledge graph" in terms
    assert "uses" not in terms


def test_schema_context_keeps_late_field_mention():
    head = "abstract " * 200
    late = "the system uses a knowledge graph over entities. " * 3
    text = head + "PAD " * 4000 + late + "end"
    clipped = schema_context(text, ["uses_knowledge_graph"], limit=1200)
    assert "knowledge graph" in clipped.lower()
    assert clipped.startswith("abstract")


def test_longer_text_prefers_full_paper():
    assert longer_text("short", "a" * 50) == "a" * 50
