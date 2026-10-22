"""Ingest a single PDF manual into a local Chroma-backed vector index.

Heavy third-party imports are kept inside build_index(), not at module
level, so this module stays importable without the full stack installed.
"""

import argparse
from pathlib import Path

from src import config, vector_store
from src.validation import validate_manual_path


def build_index(manual_path: Path) -> None:
    from llama_index.core import Settings, SimpleDirectoryReader, StorageContext, VectorStoreIndex
    from llama_index.core.node_parser import SentenceSplitter

    validate_manual_path(manual_path)

    if vector_store.get_existing_collection(manual_path) is not None:
        return

    documents = SimpleDirectoryReader(input_files=[str(manual_path)]).load_data()

    vector_store.configure_embed_model()
    Settings.node_parser = SentenceSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )

    storage_context = StorageContext.from_defaults(
        vector_store=vector_store.create_collection(manual_path)
    )

    VectorStoreIndex.from_documents(documents, storage_context=storage_context)


def ingest_and_report(manual_path: Path) -> None:
    build_index(manual_path)
    print(f"Index ready for {manual_path} in {config.STORAGE_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a single PDF manual into the vector index."
    )
    parser.add_argument("manual_path", type=Path, help="Path to the PDF manual to ingest")
    args = parser.parse_args()

    ingest_and_report(args.manual_path)


if __name__ == "__main__":
    main()
