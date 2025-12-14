#!/usr/bin/env python3
"""
Download and setup embedding and tokenizer models for Unify.

This script downloads the necessary models from HuggingFace if they don't exist locally.
Models can be stored either:
1. Locally in systems/Unify/main/models/ (recommended)
2. Used directly from HuggingFace cache

Usage:
    python setup_models.py              # Use defaults (recommended)
    python setup_models.py --use-huggingface  # Use HuggingFace cache instead of local download
"""

import argparse
import os
import sys
from pathlib import Path

# Determine paths
SCRIPT_DIR = Path(__file__).parent.resolve()
UNIFY_DIR = SCRIPT_DIR.parent
MAIN_DIR = UNIFY_DIR / "main"

# Check for scratch directory (CHPC pattern: /scratch/general/vast/u1592362)
SCRATCH_BASE = Path(os.environ.get("SCRATCH", os.environ.get("SCRATCHDIR", "")))
if not SCRATCH_BASE or not SCRATCH_BASE.exists():
    # Try CHPC default scratch pattern
    chpc_scratch = Path("/scratch/general/vast/u1592362")
    if chpc_scratch.exists():
        SCRATCH_BASE = chpc_scratch

if SCRATCH_BASE and SCRATCH_BASE.exists():
    # Use scratch for models (more space, faster I/O)
    MODELS_DIR = SCRATCH_BASE / "unify_models"
    print(f"Using scratch directory: {MODELS_DIR}")
else:
    # Fall back to local models directory
    MODELS_DIR = MAIN_DIR / "models"
    print(f"Using local directory: {MODELS_DIR}")

# Create models directory
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Model paths
TOKENIZER_LOCAL_PATH = MODELS_DIR / "tokenizer"
EMBEDDING_LOCAL_PATH = MODELS_DIR / "embedding"

# HuggingFace model names
TOKENIZER_HF_NAME = "Qwen/Qwen2.5-7B"
EMBEDDING_HF_NAME = "sentence-transformers/all-MiniLM-L6-v2"

print(f"Models directory: {MODELS_DIR}")
print(f"Tokenizer local path: {TOKENIZER_LOCAL_PATH}")
print(f"Embedding local path: {EMBEDDING_LOCAL_PATH}")
print()


def download_model(model_name: str, save_path: Path, model_type: str = "tokenizer"):
    """Download a model from HuggingFace."""
    print(f"Downloading {model_type} model: {model_name}")
    print(f"Saving to: {save_path}")
    
    if model_type == "tokenizer":
        try:
            from transformers import AutoTokenizer
            print("Loading tokenizer...")
            tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            print(f"Saving tokenizer to {save_path}...")
            tokenizer.save_pretrained(save_path)
            print(f"✓ Tokenizer saved successfully")
            return True
        except Exception as e:
            print(f"✗ Failed to download tokenizer: {e}")
            return False
    
    elif model_type == "embedding":
        try:
            from sentence_transformers import SentenceTransformer
            print("Loading embedding model...")
            model = SentenceTransformer(model_name)
            print(f"Saving embedding model to {save_path}...")
            model.save(save_path)
            print(f"✓ Embedding model saved successfully")
            return True
        except Exception as e:
            print(f"✗ Failed to download embedding model: {e}")
            return False
    
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Download and setup embedding and tokenizer models for Unify",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download models locally (recommended for CHPC)
  python setup_models.py
  
  # Use HuggingFace cache instead
  python setup_models.py --use-huggingface
  
  # Custom models
  python setup_models.py --tokenizer llama2 --embedding all-MiniLM-L6-v2
        """
    )
    
    parser.add_argument(
        "--use-huggingface",
        action="store_true",
        help="Use HuggingFace cache instead of downloading locally (not recommended for CHPC)"
    )
    
    parser.add_argument(
        "--tokenizer",
        type=str,
        default=TOKENIZER_HF_NAME,
        help=f"HuggingFace tokenizer model name (default: {TOKENIZER_HF_NAME})"
    )
    
    parser.add_argument(
        "--embedding",
        type=str,
        default=EMBEDDING_HF_NAME,
        help=f"HuggingFace embedding model name (default: {EMBEDDING_HF_NAME})"
    )
    
    args = parser.parse_args()
    
    print("="*70)
    print("UNIFY MODEL SETUP")
    print("="*70)
    print()
    
    if args.use_huggingface:
        print("Mode: Use HuggingFace cache")
        print(f"Tokenizer: {args.tokenizer}")
        print(f"Embedding: {args.embedding}")
        print()
        print("✓ Models will be downloaded to HuggingFace cache on first use")
        print(f"  Cache location: {os.path.expanduser('~/.cache/huggingface')}")
        print()
        
        # Create marker files indicating HuggingFace mode
        marker_file = MODELS_DIR / ".huggingface_mode"
        with open(marker_file, "w") as f:
            f.write(f"tokenizer: {args.tokenizer}\n")
            f.write(f"embedding: {args.embedding}\n")
        
        print("✓ Configuration saved to: " + str(marker_file))
        return 0
    
    else:
        print("Mode: Download models locally (CHPC-compatible)")
        print(f"Tokenizer: {args.tokenizer}")
        print(f"Embedding: {args.embedding}")
        print()
        
        success = True
        
        # Download tokenizer
        if TOKENIZER_LOCAL_PATH.exists():
            print(f"✓ Tokenizer already exists at {TOKENIZER_LOCAL_PATH}")
        else:
            print(f"\n[1/2] Downloading tokenizer...")
            if not download_model(args.tokenizer, TOKENIZER_LOCAL_PATH, "tokenizer"):
                print("✗ Failed to download tokenizer")
                success = False
        
        # Download embedding
        if EMBEDDING_LOCAL_PATH.exists():
            print(f"✓ Embedding model already exists at {EMBEDDING_LOCAL_PATH}")
        else:
            print(f"\n[2/2] Downloading embedding model...")
            if not download_model(args.embedding, EMBEDDING_LOCAL_PATH, "embedding"):
                print("✗ Failed to download embedding model")
                success = False
        
        print()
        print("="*70)
        
        if success:
            print("✓ ALL MODELS READY")
            print(f"Tokenizer: {TOKENIZER_LOCAL_PATH}")
            print(f"Embedding: {EMBEDDING_LOCAL_PATH}")
            print()
            print("You can now run preprocessing:")
            print("  python systems/Unify/scripts/preprocess_unify_data.py --datasets all")
            return 0
        else:
            print("✗ SOME MODELS FAILED TO DOWNLOAD")
            print()
            print("Troubleshooting:")
            print("1. Check internet connection")
            print("2. Try downloading individual models with custom names")
            print("3. Use --use-huggingface to defer downloads to HuggingFace cache")
            return 1


if __name__ == "__main__":
    sys.exit(main())

