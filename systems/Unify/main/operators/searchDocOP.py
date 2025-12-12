from .genPromptOP import genPromptOP
from utils.llm_config import clean_llm_response

class searchDocOP:
    def __init__(self, query):
        self.query = query


    def execute(self, LLMclient, chatModel, ctxManager, useGenPrompt=False):

        if useGenPrompt:
            use_prompt = genPromptOP(self.prompt).execute(LLMclient, ctxManager)
        else:
            use_prompt = self.prompt
        ctxManager.add_user_message(use_prompt)


        res = chatModel.create_completion(
            LLMclient,
            temperature=0.1,
            top_p=0.9,
            max_tokens=500,  # Increased for reasoning models like qwen3 that output <think> blocks
            messages=ctxManager.get_messages()
        )
        # Clean the response to remove <think> tags from models like qwen3
        res = clean_llm_response(res)
        print("Executed results: ")
        print(res)

        ctxManager.add_assistant_message(res)
        return ctxManager



