import bz2
import json
import os

# Force CPU to avoid CUDA compatibility issues on some clusters
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from transformers import AutoTokenizer
from sentence_transformers import SentenceTransformer
import torch

SENTENTENCE_TRANSFORMER_BATCH_SIZE = 128  # TUNE THIS VARIABLE depending on the size of your embedding model and GPU mem available


class EmbedModel:
    def __init__(self, tokenizer_path, sentence_model_path):
        # DEBUG: Print URIs/paths
        print(f"[DEBUG] tokenizer_path: {tokenizer_path}")
        print(f"[DEBUG] sentence_model_path: {sentence_model_path}")

        # Load tokenizer (AutoTokenizer supports various model types including LLaMA, Qwen, etc.)
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=True)

        # Force sentence-transformer to run on CPU to avoid unsupported GPU errors
        self.device = torch.device("cpu")
        self.sentence_model = SentenceTransformer(
            sentence_model_path,
            device=self.device,
        )

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