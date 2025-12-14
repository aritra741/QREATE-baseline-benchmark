import bz2
import json
import os

from transformers import AutoTokenizer
from sentence_transformers import SentenceTransformer
import torch

# Disable CUDA for HPC compatibility
os.environ['CUDA_VISIBLE_DEVICES'] = ''
torch.cuda.is_available = lambda: False

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

        # Use CPU only for HPC compatibility
        self.device = torch.device("cpu")
        print(f"[DEBUG] Using device: {self.device}")
        
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