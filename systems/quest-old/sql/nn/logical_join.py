from .base import Logical

class LogicalJoin(Logical):
    """
    Info :  join_type - a list of join type ['INNER', ..]
            join_order - a list of BinaryNode U.a1 == V.a2 by tuple, [U.a1 == V.a2 , Team.team == Player.teamname]
            type - the extract type ('Photo'/'Text'/..)
            
    Per QUEST Paper Section 3.2 - Join Transformation:
            extracted_join_attr - the join attribute to extract from first table
            join_filter_attr - the join attribute to use as IN filter on second table
            
    Input : LogicalFilter / LogicalJoin / LogicalExtract ..
    """
    def __init__(self, join_type, join_order, type, extracted_join_attr=None, join_filter_attr=None):
        super().__init__()
        self.join_type = join_type
        self.join_order = join_order
        self.type = type
        self.name = 'LogicalJoin'
        # Per QUEST paper: store join attributes for IN filter transformation
        self.extracted_join_attr = extracted_join_attr  # attribute extracted from first table
        self.join_filter_attr = join_filter_attr  # attribute to filter second table with