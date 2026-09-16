from quwarts.core.logical import infer_logical_schema


def test_infer_includes_unqualified_columns_from_workload_sql():
    sql = (
        "SELECT birth_continent, COUNT(*) AS artist_count "
        "FROM art WHERE tone != '' GROUP BY birth_continent"
    )
    logical = infer_logical_schema([sql])
    attrs = {(item.entity_type, item.name) for item in logical.attributes}
    assert "art" in logical.entity_types
    assert ("art", "birth_continent") in attrs
    assert ("art", "tone") in attrs
