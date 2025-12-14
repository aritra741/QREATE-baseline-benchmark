#to run unify, you should specify the Ollama model name, tokenizer and embeded model first
#--doc_path is the path of your document set
#--llm_model_path should be an Ollama model name (e.g., qwen3:8b)
#--api_base defaults to http://localhost:11434/v1 (Ollama's default)
python unify.py --llm_model_path qwen3:8b --tokenizer_path /path/to/tokenizer --sentence_model_path /path/to/sentence_model --doc_path /path/to/docs --query /your/query --api_base http://localhost:11434/v1