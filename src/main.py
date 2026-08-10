"""
parse -> read -> solve -> write

Run with:
    python -m src.main --input data/raw/raw_data.xlsx
    python -m src.main                   # uses the default path below
    python -m src.main --skip-parse      # reuse cached JSON, skip Excel
"""
import argparse
from pathlib import Path
from src.instance import parse_workbook, load_cached_instances, cache_instances
from src.model import solve_instance as solve_milp_model
from src.model_cpsat import solve_cpsat
from src.utils import write_output, generate_comparison_table
from src.vis import plot_gantt_chart


OUTPUT_DIR = Path("outputs")
TIME_LIMIT = 1500000
CPSAT_TIME_LIMIT = 300000


def run(input_file: str, skip_parse: bool = False):
    # Load instances
    if not skip_parse:
        input_path = Path(input_file)
        if not input_path.is_file():
            raise FileNotFoundError(f"Input file not found: {input_file}")
        instances = parse_workbook(input_file)
        cache_instances(instances, Path('data/processed'))
    else:
        instances = load_cached_instances(Path('data/processed'))
    
    # Results storage for comparison tables
    results = {"milp": [], "cpsat": []}

    for inst in instances:
        print(f"Solving {inst.name} ...")
        
        # Create instance-specific output folder
        instance_slug = inst.name.lower().replace(" ", "_")
        instance_dir = OUTPUT_DIR / instance_slug
        instance_dir.mkdir(parents=True, exist_ok=True)
        
        milp_res = solve_milp_model(inst, time_limit_ms=TIME_LIMIT)
        cpsat_res = solve_cpsat(inst, time_limit_ms=CPSAT_TIME_LIMIT)

        milp_res["instance_name"] = inst.name
        cpsat_res["instance_name"] = inst.name

        results["milp"].append(milp_res)
        results["cpsat"].append(cpsat_res)

        # Write Output JSONs
        write_output(instance_slug, "milp", milp_res, instance_dir)
        write_output(instance_slug, "cpsat", cpsat_res, instance_dir)

        # Plot Gantt Charts
        gantt_milp_path = instance_dir / f"{instance_slug}_gantt_milp.png"
        plot_gantt_chart(inst.name + " (MILP - SCIP)", milp_res.get("schedule", []), gantt_milp_path)

        gantt_cpsat_path = instance_dir / f"{instance_slug}_gantt_cpsat.png"
        plot_gantt_chart(inst.name + " (CP-SAT)", cpsat_res.get("schedule", []), gantt_cpsat_path)

        print(f"Completed {inst.name}")

    # Export Summary Comparison Table
    print("Generating comparison table...")
    # comparison table
    generate_comparison_table(
        approaches=[
            ("MILP (SCIP)", results["milp"]),
            ("CP-SAT", results["cpsat"]),
        ],
        output_dir=OUTPUT_DIR,
    )
    
    print(f"\nAll done! Results in {OUTPUT_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run IEDO scheduling MILP pipeline")
    parser.add_argument("--input", type=str, default="data/raw/raw_data.xlsx", help="Path to input Excel file")
    parser.add_argument("--skip-parse", action="store_true", help="Reuse cached JSON, skip Excel parsing")
    args = parser.parse_args()
    run(args.input, skip_parse=args.skip_parse)