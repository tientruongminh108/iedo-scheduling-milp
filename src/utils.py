import json
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List


def write_output(instance_slug: str, approach: str, result: Dict[str, Any], output_directory: Path) -> Path:
    """
    Exports optimization results for a given instance into a JSON file.

    Args:
        instance_slug: Slugified instance name (e.g., "instance_01").
        approach: Approach name ("two_stage" or "weighted_sum").
        result: Dictionary containing solver output (status, metrics, schedule).
        output_directory: Directory path where output JSON files will be stored.

    Returns:
        Path: Full path to the generated JSON output file.
    """
    target_dir = Path(output_directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{instance_slug}_{approach}_result.json"
    out_file_path = target_dir / file_name

    output_data = {
        "instance_name": result.get("instance_name"),
        "approach": approach,
        "status": result.get("status"),
        "makespan": result.get("makespan"),
        "tardy_jobs": result.get("tardy_jobs"),
        "solver_time_ms": result.get("solver_time_ms"),
        "schedule": result.get("schedule", [])
    }

    with open(out_file_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=4)

    print(f"Saved {approach} result for {instance_slug} to {out_file_path}")
    return out_file_path


def generate_comparison_table(
    approaches: List[tuple],
    output_dir: Path = Path("outputs")
) -> str:
    """Generates and saves a comparison summary table across instances."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not approaches:
        raise ValueError("No approach results provided.")

    # build per-approach maps keyed by instance name
    approach_maps = []
    for name, results in approaches:
        m = {
            r.get("instance_name") or f"Instance {i+1}": r
            for i, r in enumerate(results)
        }
        approach_maps.append((name, m))

    all_instances = sorted(
        set().union(*(m.keys() for _, m in approach_maps))
    )

    # assemble comparison rows
    comparison_data = []
    for inst in all_instances:
        row: Dict[str, Any] = {"Instance": inst}
        for name, m in approach_maps:
            r = m.get(inst, {})
            mk = r.get("makespan")
            row[f"{name} - Status"] = r.get("status", "N/A")
            row[f"{name} - Tardy"] = r.get("tardy_jobs", "N/A")
            row[f"{name} - Makespan (h)"] = (
                round(mk, 2) if isinstance(mk, (int, float)) else "N/A"
            )
            row[f"{name} - Time (ms)"] = r.get("solver_time_ms", "N/A")
        comparison_data.append(row)

    df = pd.DataFrame(comparison_data)
    
    # Save Markdown file only (no CSV)
    md_table = df.to_markdown(index=False)
    md_path = output_dir / "approach_comparison.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Solving Results Summary\n\n")
        f.write(md_table)

    print(f"\nSummary table saved to {md_path}")
    return md_table