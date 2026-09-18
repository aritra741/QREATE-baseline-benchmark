from __future__ import annotations

from quwarts.eval.phase1_med import evidence_sha, first_cause, first_change


def test_first_change_marks_materialize() -> None:
    assert first_change("oral", "oral", None, None, None) == "materialized_column"
    assert first_change("oral", None, None, None, None) == "repaired_evidence"
    assert first_change("oral", "oral", "oral", False, None) == "sql_result"


def test_first_cause_join_before_filter() -> None:
    assert first_cause(
        sql="SELECT a FROM t JOIN u ON t.k=u.k WHERE t.x <> ''",
        gold_rows=3, pred_rows=0, matched=0, cell_ok=False,
        unfiltered_rows=4, gold_keys_in_corpus=True, near=False,
    ) == "join_failure"
    assert first_cause(
        sql="SELECT a FROM t WHERE t.x <> ''",
        gold_rows=3, pred_rows=0, matched=0, cell_ok=False,
        unfiltered_rows=4, gold_keys_in_corpus=True, near=False,
    ) == "predicate_false_negative"


def test_evidence_sha_changes_when_surface_changes() -> None:
    from quwarts.core.extract import EvidenceStore
    from quwarts.core.models import EvidenceRecord

    store = EvidenceStore()
    rec = EvidenceRecord(
        key="k", segment_id="s", doc_id="d", attribute="t.a",
        surface_value="x", extractor_cfg_hash="h", quality_tier="cheap", stage=1,
    )
    store.put(rec)
    before = evidence_sha(store)
    store.records["k"] = rec.model_copy(update={"surface_value": "y"})
    assert evidence_sha(store) != before
