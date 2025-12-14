import bz2
import json
import os

from transformers import AutoTokenizer
from sentence_transformers import SentenceTransformer
import torch

SENTENTENCE_TRANSFORMER_BATCH_SIZE = 128  # TUNE THIS VARIABLE depending on the size of your embedding model and GPU mem available


class EmbedModel:
    def __init__(self, tokenizer_path, sentence_model_path):
        # DEBUG: Print URIs/paths
        print(f"[DEBUG] tokenizer_path: {tokenizer_path}")
        print(f"[DEBUG] sentence_model_path: {sentence_model_path}")
        print(f"[DEBUG] CUDA available: {torch.cuda.is_available()}")

        # Load tokenizer (AutoTokenizer supports various model types including LLaMA, Qwen, etc.)
        print(f"[DEBUG] Loading tokenizer from {tokenizer_path}...")
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=True)
        print(f"[DEBUG] Tokenizer loaded successfully")

        # Use GPU if available, otherwise fall back to CPU
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
            print(f"[DEBUG] Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            self.device = torch.device("cpu")
            print(f"[DEBUG] Using CPU (GPU not available)")
        
        print(f"[DEBUG] Loading SentenceTransformer from {sentence_model_path}...")
        self.sentence_model = SentenceTransformer(
            sentence_model_path,
            device=self.device,
        )
        print(f"[DEBUG] SentenceTransformer loaded successfully")

    def calculate_embeddings(self, sentences):
        """
        Compute normalized embeddings for a list of sentences using a sentence encoding model.

        This function leverages multiprocessing to encode the sentences, which can enhance the
        processing speed on multi-core machines.

        Args:
            sentences (List[str]): A list of sentences for which embeddings are to be computed.

        Returns:
            np.ndarray: An array of normalized embeddings for the given sentences.

        """
        embeddings = self.sentence_model.encode(
            sentences=sentences,
            normalize_embeddings=True,
            batch_size=SENTENTENCE_TRANSFORMER_BATCH_SIZE,
        )
        return embeddings