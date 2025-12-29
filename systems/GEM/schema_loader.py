"""
Schema Loader - Induction Module

Reads attribute definitions from JSON files and converts them into
a structured format suitable for LLM System Prompts.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Attribute:
    """Represents a single attribute in the schema."""
    name: str
    type: str
    description: str
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description
        }
    
    def to_prompt_str(self) -> str:
        """Convert to LLM-friendly string for system prompt."""
        return f"- {self.name} ({self.type}): {self.description}"


@dataclass
class Schema:
    """Represents a complete schema for an entity."""
    entity_name: str
    attributes: List[Attribute]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_name": self.entity_name,
            "attributes": [attr.to_dict() for attr in self.attributes]
        }
    
    def to_prompt_str(self) -> str:
        """Convert to LLM-friendly system prompt text."""
        lines = [
            f"Entity: {self.entity_name}",
            "Extract the following fields:",
            ""
        ]
        for attr in self.attributes:
            lines.append(attr.to_prompt_str())
        return "\n".join(lines)
    
    def get_key_attributes(self) -> List[str]:
        """Get attributes that should be used as entity keys for blocking.
        
        Typically, the first string attribute is the entity identifier.
        """
        for attr in self.attributes:
            type_lower = attr.type.lower()
            if type_lower in ["string", "text", "name", "str", "multi_str"]:
                return [attr.name]
        
        # Fallback: return all string attributes
        return [attr.name for attr in self.attributes if attr.type.lower() in ["string", "text", "name", "str", "multi_str"]]
    
    def get_numeric_attributes(self) -> List[str]:
        """Get numeric attributes for aggregation queries."""
        return [attr.name for attr in self.attributes if attr.type.lower() in ["int", "integer", "float", "double", "number", "numeric", "int_value", "float_value"]]


class SchemaLoader:
    """Loads and manages schema definitions from JSON files."""
    
    def __init__(self):
        """Initialize the schema loader."""
        self.schemas: Dict[str, Schema] = {}
    
    def load_from_file(self, filepath: Path) -> Schema:
        """Load schema from a JSON file.
        
        Expected format:
        {
            "entity_name": "disease",
            "attributes": {
                "disease_name": {
                    "type": "string",
                    "description": "The name of the disease"
                },
                "disease_type": {
                    "type": "string",
                    "description": "Type of disease (infectious, genetic, etc.)"
                }
            }
        }
        
        Args:
            filepath: Path to the JSON schema file
            
        Returns:
            Schema object
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Schema file not found: {filepath}")
        
        with open(filepath, "r") as f:
            data = json.load(f)
        
        return self._parse_schema(data)
    
    def _parse_schema(self, data: Dict[str, Any]) -> Schema:
        """Parse raw schema data into Schema object.
        
        Handles multiple formats:
        - Format 1: {"entity_name": "...", "attributes": {"attr": {"type": "...", "description": "..."}}}
        - Format 2: {"entity_name": {"attr": {"value_type": "...", "description": "..."}}}
        - Format 3: UDA-Bench format with value_type, usage, modality, etc.
        
        Args:
            data: Dictionary containing schema definition
            
        Returns:
            Schema object
        """
        entity_name = data.get("entity_name", "unknown")
        attributes_data = data.get("attributes", {})
        
        # If no "attributes" key, check if data has entity as key
        if not attributes_data and entity_name == "unknown":
            # Find the first non-standard key that looks like an entity
            for key, val in data.items():
                if isinstance(val, dict) and not key.startswith("_"):
                    entity_name = key
                    attributes_data = val
                    break
        
        attributes = []
        for attr_name, attr_info in attributes_data.items():
            if isinstance(attr_info, dict):
                # Extract type - try multiple keys
                attr_type = (
                    attr_info.get("type") or
                    attr_info.get("field_type") or
                    attr_info.get("value_type", "string")
                )
                
                # Extract description - try multiple keys
                attr_desc = (
                    attr_info.get("description") or
                    attr_info.get("field_description") or
                    f"The {attr_name} field"
                )
                
                # Clean up description if it's very long
                if len(attr_desc) > 500:
                    attr_desc = attr_desc[:500] + "..."
            else:
                # Fallback: treat as string description
                attr_type = "string"
                attr_desc = str(attr_info)
            
            attributes.append(Attribute(
                name=attr_name,
                type=attr_type,
                description=attr_desc
            ))
        
        schema = Schema(entity_name=entity_name, attributes=attributes)
        self.schemas[entity_name] = schema
        return schema
    
    def get_schema(self, entity_name: str) -> Optional[Schema]:
        """Get a cached schema by entity name.
        
        Args:
            entity_name: Name of the entity
            
        Returns:
            Schema object or None if not found
        """
        return self.schemas.get(entity_name)
    
    def load_multiple(self, directory: Path) -> Dict[str, Schema]:
        """Load all schema files from a directory.
        
        Expects files named like: {entity_name}_attributes.json or {entity_name}.json
        
        Args:
            directory: Path to directory containing schema files
            
        Returns:
            Dictionary mapping entity name to Schema
        """
        directory = Path(directory)
        if not directory.exists():
            raise FileNotFoundError(f"Schema directory not found: {directory}")
        
        schemas = {}
        for json_file in directory.glob("*_attributes.json"):
            try:
                schema = self.load_from_file(json_file)
                schemas[schema.entity_name] = schema
            except Exception as e:
                print(f"Warning: Failed to load schema from {json_file}: {e}")
        
        return schemas


# Global loader instance
_loader = SchemaLoader()


def load_schema(filepath: Path) -> Schema:
    """Convenience function to load a schema from file.
    
    Args:
        filepath: Path to schema JSON file
        
    Returns:
        Schema object
    """
    return _loader.load_from_file(filepath)


def load_schemas(directory: Path) -> Dict[str, Schema]:
    """Convenience function to load all schemas from a directory.
    
    Args:
        directory: Path to directory with schema files
        
    Returns:
        Dictionary mapping entity name to Schema
    """
    return _loader.load_multiple(directory)

