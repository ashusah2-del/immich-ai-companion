import argparse

from . import db

COLUMNS = [
    ("id", "ID", 4),
    ("kind", "Kind", 7),
    ("original_filename", "Original", 26),
    ("prompt_title", "Prompt", 26),
    ("prompt_category", "Category", 20),
    ("status", "Status", 8),
    ("created_at", "Created", 19),
]


def _truncate(value, width):
    value = "" if value is None else str(value)
    return value if len(value) <= width else value[: width - 1] + "…"


def print_report(kind=None, limit=None):
    runs = db.get_run_history(kind=kind, limit=limit)

    if not runs:
        print("No runs recorded yet.")
        return

    header = "  ".join(label.ljust(width) for _, label, width in COLUMNS)
    print(header)
    print("-" * len(header))
    for run in runs:
        row = "  ".join(_truncate(run.get(key), width).ljust(width) for key, _, width in COLUMNS)
        print(row)
        if run["status"] == "failed" and run["error"]:
            print(f"    error: {run['error']}")

    counts = {}
    for run in runs:
        counts[(run["kind"], run["status"])] = counts.get((run["kind"], run["status"]), 0) + 1
    print("-" * len(header))
    summary = ", ".join(f"{k[0]}/{k[1]}={v}" for k, v in sorted(counts.items()))
    print(f"Total: {len(runs)}  ({summary})")


def main():
    parser = argparse.ArgumentParser(description="Show enhancement/design run history against the prompt library.")
    parser.add_argument("--kind", choices=["restore", "design"], help="Filter to only this worker's runs.")
    parser.add_argument("--limit", type=int, help="Limit to the N most recent runs.")
    args = parser.parse_args()
    print_report(kind=args.kind, limit=args.limit)


if __name__ == "__main__":
    main()
