import numpy as np

class joinOP:
    def __init__(self, dataSet1, dataSet2, joinAtt1, joinAtt2, cond=None):
        self.dataSet1 = dataSet1
        self.dataSet2 = dataSet2
        self.joinAtt1 = joinAtt1
        self.joinAtt2 = joinAtt2
        self.opName = "Join"

    def execute(self, LLMclient, chatModel, ctxManager):
        # join dataSet1 and dataSet2 on joinAtt1 == joinAtt2
        joinResult = self.join(self.dataSet1, self.dataSet2, self.joinAtt1, self.joinAtt2)
        return joinResult, ctxManager

    def join(self, dataSet1, dataSet2, joinAtt1, joinAtt2):
        joinResult = []
        
        # Handle edge cases where inputs might be strings or None
        if isinstance(dataSet1, str) or dataSet1 is None:
            return joinResult
        if isinstance(dataSet2, str) or dataSet2 is None:
            return joinResult
        
        # Ensure inputs are iterable
        if not hasattr(dataSet1, '__iter__'):
            return joinResult
        if not hasattr(dataSet2, '__iter__'):
            return joinResult
        
        try:
            for item1 in dataSet1:
                for item2 in dataSet2:
                    # Skip if items are strings or not dict-like
                    if isinstance(item1, str) or isinstance(item2, str):
                        continue
                    if not hasattr(item1, '__getitem__') or not hasattr(item2, '__getitem__'):
                        continue
                    
                    try:
                        if item1[joinAtt1] == item2[joinAtt2]:
                            joinResult.append({**item1, **item2})
                    except (KeyError, TypeError):
                        # Skip items that don't have the join attributes
                        continue
        except TypeError:
            # If iteration fails, return empty result
            pass
        
        return joinResult