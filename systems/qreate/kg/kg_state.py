import networkx as nx
from typing import List, Dict, Any

class QREATEKGState:
    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self.alias_map = {} # normalized_name -> canonical_name

    def add_triple(self, triple: Dict[str, Any], sub_id: str, obj_id: str = None):
        sub = sub_id
        pred = triple.get('pred', '').lower().strip()
        obj = triple.get('obj')
        role = triple.get('role', 'ATTRIBUTE').upper()
        obj_type = triple.get('object_type', 'LITERAL').upper()

        if not self.graph.has_node(sub):
            self.graph.add_node(sub, attributes={}, entity_type=None)

        node_data = self.graph.nodes[sub]
        if 'attributes' not in node_data:
            node_data['attributes'] = {}

        if role == 'TYPE':
            # Store the entity type separately for table discovery
            node_data['entity_type'] = str(obj).strip() if obj else None
        elif role == 'RELATIONSHIP' and obj_type == 'ENTITY' and obj_id:
            # Add as graph edge
            if not self.graph.has_node(obj_id):
                self.graph.add_node(obj_id, attributes={}, entity_type=None)
            self.graph.add_edge(sub, obj_id, predicate=pred)
        else:
            # ATTRIBUTE: Add as node property
            node_data['attributes'][pred] = obj

    def get_all_triples(self):
        return self.graph
