"""Live verification of semantic memory with NVIDIA embeddings.

Run: python scripts/verify_semantic_memory.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from friday.models.providers.nvidia_provider import NvidiaProvider
from friday.memory.semantic import SemanticMemory, Fact
import tempfile


def main():
    print("=" * 55)
    print("Semantic Memory — Live Embedding Verification")
    print("=" * 55)

    nvidia = NvidiaProvider()
    print(f"\nNVIDIA available: {nvidia.available}")

    with tempfile.TemporaryDirectory() as tmp:
        sem = SemanticMemory(f"{tmp}/sem.json", embedding_provider=nvidia)
        print(f"Embeddings enabled: {sem.has_embeddings}")

        # Add facts
        print("\nAdding facts...")
        facts = [
            Fact(content="Shreesh prefers DOM access over screenshots", category="preference"),
            Fact(content="FRIDAY uses NVIDIA NIM as primary model provider", category="general"),
            Fact(content="The capital of France is Paris", category="general"),
            Fact(content="Python is the primary language for the backend", category="general"),
        ]
        sem.add_facts(facts)
        print(f"Stored {sem.total_facts} facts")

        # Semantic search
        print("\n--- Semantic Search Test ---")
        query = "how should the system perceive the screen?"
        print(f"Query: {query}")
        results = sem.search(query, top_k=2)
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.category}] {r.content}")

        print("\n--- Another Query ---")
        query2 = "what model does FRIDAY use?"
        print(f"Query: {query2}")
        results2 = sem.search(query2, top_k=2)
        for i, r in enumerate(results2, 1):
            print(f"{i}. [{r.category}] {r.content}")

    print("\n" + "=" * 55)
    print("Verification complete.")
    print("=" * 55)


if __name__ == "__main__":
    main()
