from __future__ import annotations

import argparse
import json

from agentic_scd.rag.retriever import rebuild_vector_store, retriever_stats


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agentic-scd-vectorize")
    parser.add_argument(
        "--collection",
        action="append",
        dest="collections",
        help="Rebuild only the named collection. Repeat the flag to rebuild multiple collections.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the rebuild result as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = rebuild_vector_store(args.collections)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return
    stats = retriever_stats()
    print(f"Vector backend: {stats['backend']}")
    print(f"Vector store: {stats['vector_store_path']}")
    for name, count in result["collections"].items():
        print(f"{name}: {count} documents")


if __name__ == "__main__":
    main()
