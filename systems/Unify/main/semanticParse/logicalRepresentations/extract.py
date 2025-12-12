# Per paper Table 1: Extract operator - Input: Text, Output: Text
# Logical Representation: "get [Entity] from documents"
EXTRACT_LR = {
        "Question": "Get [Entity] from documents",
        "IDQuestion": "Get [Entity1] from documents",
        "Plan": [
            {
                "Extract": ["[Entity]"]
            }
        ],
        "IDPlan":[
                {
                    "Operator":"Extract",
                    "Parameter":["[Entity1]"],
                    "Followup Plan" : []
                }
        ],
        "Return": "[Entity]"
    }

# Additional extract pattern for answering specific questions
EXTRACT_LR_2 = {
        "Question": "Answer [Entity] from documents",
        "IDQuestion": "Answer [Entity1] from documents",
        "Plan": [
            {
                "Extract": ["[Entity]"]
            }
        ],
        "IDPlan":[
                {
                    "Operator":"Extract",
                    "Parameter":["[Entity1]"],
                    "Followup Plan" : []
                }
        ],
        "Return": "[Entity]"
    }
