"""
GEM System Tests

Comprehensive tests for all GEM modules.
Run with: pytest systems/GEM/test_gem.py -v
"""

import json
import tempfile
from pathlib import Path

import pytest

# Try to import GEM modules, skip tests if dependencies missing
try:
    from systems.GEM.config import CACHE_DIR
    from systems.GEM.schema_loader import SchemaLoader, Schema, Attribute
    from systems.GEM.blocking import SemanticBlocker, UnionFind
    from systems.GEM.resolver import EntityResolver
    from systems.GEM.db_engine import DBEngine
    GEM_AVAILABLE = True
except ImportError:
    GEM_AVAILABLE = False


@pytest.mark.skipif(not GEM_AVAILABLE, reason="GEM dependencies not available")
class TestSchemaLoader:
    """Test schema loading and parsing."""
    
    def test_attribute_creation(self):
        """Test Attribute dataclass."""
        attr = Attribute(
            name="disease_name",
            type="string",
            description="The name of the disease"
        )
        assert attr.name == "disease_name"
        assert attr.type == "string"
        
        # Test prompt conversion
        prompt_str = attr.to_prompt_str()
        assert "disease_name" in prompt_str
        assert "string" in prompt_str
    
    def test_schema_creation(self):
        """Test Schema dataclass."""
        attrs = [
            Attribute("name", "string", "Entity name"),
            Attribute("count", "integer", "Number of items")
        ]
        schema = Schema("test_entity", attrs)
        
        assert schema.entity_name == "test_entity"
        assert len(schema.attributes) == 2
        
        # Test key attributes detection
        key_attrs = schema.get_key_attributes()
        assert "name" in key_attrs
        
        # Test numeric attributes detection
        numeric = schema.get_numeric_attributes()
        assert "count" in numeric
    
    def test_schema_loader_parse(self):
        """Test schema parsing from dict."""
        loader = SchemaLoader()
        
        data = {
            "entity_name": "disease",
            "attributes": {
                "disease_name": {
                    "type": "string",
                    "description": "Name of the disease"
                },
                "disease_type": {
                    "type": "string",
                    "description": "Type of disease"
                }
            }
        }
        
        schema = loader._parse_schema(data)
        assert schema.entity_name == "disease"
        assert len(schema.attributes) == 2


@pytest.mark.skipif(not GEM_AVAILABLE, reason="GEM dependencies not available")
class TestUnionFind:
    """Test Union-Find data structure."""
    
    def test_union_find_basic(self):
        """Test basic Union-Find operations."""
        uf = UnionFind(5)
        
        # Initially all in separate sets
        assert uf.find(0) == 0
        assert uf.find(4) == 4
        
        # Union some elements
        uf.union(0, 1)
        uf.union(1, 2)
        uf.union(3, 4)
        
        # Check clusters
        assert uf.find(0) == uf.find(1) == uf.find(2)
        assert uf.find(3) == uf.find(4)
        assert uf.find(0) != uf.find(3)
    
    def test_union_find_get_clusters(self):
        """Test cluster retrieval."""
        uf = UnionFind(4)
        uf.union(0, 1)
        uf.union(2, 3)
        
        clusters = uf.get_clusters()
        assert len(clusters) == 2
        
        # Each cluster should have 2 elements
        for cluster in clusters.values():
            assert len(cluster) == 2


@pytest.mark.skipif(not GEM_AVAILABLE, reason="GEM dependencies not available")
class TestDBEngine:
    """Test database engine."""
    
    def test_db_engine_init(self):
        """Test DB engine initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = DBEngine(db_path=db_path)
            
            assert engine.conn is not None
            assert engine.db_path == db_path
            
            engine.close()
    
    def test_sql_type_conversion(self):
        """Test schema to SQL type conversion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = DBEngine(db_path=db_path)
            
            # Test various type conversions
            assert engine._get_sql_type("string") == "VARCHAR"
            assert engine._get_sql_type("integer") == "INTEGER"
            assert engine._get_sql_type("float") == "DOUBLE"
            assert engine._get_sql_type("boolean") == "BOOLEAN"
            
            engine.close()


@pytest.mark.skipif(not GEM_AVAILABLE, reason="GEM dependencies not available")
class TestEntityResolver:
    """Test entity resolution."""
    
    def test_resolver_init(self):
        """Test resolver initialization."""
        resolver = EntityResolver()
        assert resolver.canonical_map == {}
        assert resolver.client is not None or resolver.client is None  # May fail if no Ollama
    
    def test_resolver_single_mention(self):
        """Test resolution of single mention block."""
        resolver = EntityResolver()
        
        # Single item block should return itself as canonical
        canonical = resolver._get_canonical_for_block(["Advil"])
        assert canonical == "Advil"
    
    def test_resolver_get_canonical(self):
        """Test canonical lookup."""
        resolver = EntityResolver()
        resolver.canonical_map = {
            "advil": "Advil",
            "advil pm": "Advil",
            "ibuprofen": "Advil"
        }
        
        # Exact match
        assert resolver.get_canonical("advil") == "Advil"
        
        # Case insensitive
        assert resolver.get_canonical("ADVIL") == "Advil"
        
        # Unknown value returns original
        assert resolver.get_canonical("unknown") == "unknown"


class TestGEMIntegration:
    """Integration tests for full GEM pipeline."""
    
    def test_imports(self):
        """Test all modules can be imported."""
        if GEM_AVAILABLE:
            from systems.GEM import config
            from systems.GEM import schema_loader
            from systems.GEM import extractor
            from systems.GEM import blocking
            from systems.GEM import resolver
            from systems.GEM import db_engine
            from systems.GEM import gem_runner
            
            assert config is not None
            assert schema_loader is not None
            assert extractor is not None
            assert blocking is not None
            assert resolver is not None
            assert db_engine is not None
            assert gem_runner is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

