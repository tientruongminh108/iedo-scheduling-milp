import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import FuncFormatter
from pathlib import Path
from typing import Dict, Any, List


def _format_time(x, _):
    """Helper function to convert decimal hours (e.g., 7.5) into HH:MM format (07:30)."""
    hours = int(x) % 24
    minutes = int(round((x % 1) * 60))
    if minutes == 60:
        hours = (hours + 1) % 24
        minutes = 0
    return f"{hours:02d}:{minutes:02d}"


def plot_gantt_chart(instance_name: str, schedule: List[Dict[str, Any]], output_path: Path) -> None:
    """Generates and saves a Gantt chart representing the scheduling timeline per machine."""
    if not schedule:
        print(f"[{instance_name}] No schedule data available to plot Gantt chart.")
        return

    # Extract unique machine IDs and sort them for the Y-axis
    machine_ids = sorted(list(set(task["machine_id"] for task in schedule)))
    machine_y_indices = {m_id: idx for idx, m_id in enumerate(machine_ids)}

    # Dynamically scale figure height based on the number of machines
    fig_height = max(4.0, len(machine_ids) * 1.2)
    fig, ax = plt.subplots(figsize=(12, fig_height))

    # Color palette per Job
    cmap = plt.get_cmap("tab20")
    unique_jobs = sorted(list(set(task["job_id"] for task in schedule)))
    job_color_map = {job_id: cmap(i % 20) for i, job_id in enumerate(unique_jobs)}

    # Station opening time offset (7:30 AM = 7.5 hours)
    OPENING_TIME = 7.5

    # Draw Gantt bars for each scheduled task
    zero_duration_count = 0
    for task in schedule:
        job_id = task["job_id"]
        piece = task["piece"]
        m_id = task["machine_id"]
        
        # Shift start time to align with the 7:30 AM opening baseline
        start = task["start"] + OPENING_TIME
        duration = task["duration"]

        if duration <= 0:
            zero_duration_count += 1
            continue

        y_pos = machine_y_indices[m_id]
        color = job_color_map[job_id]

        # Draw horizontal bar for task duration
        ax.broken_barh(
            [(start, duration)],
            (y_pos - 0.25, 0.5),
            facecolors=color,
            edgecolor="black",
            linewidth=0.8,
            alpha=0.85
        )

        # Draw text label inside bar: e.g., "J1-P1" or "J1-P2"
        label = f"J{job_id}-P{piece}"
        ax.text(
            start + duration / 2.0,
            y_pos,
            label,
            ha="center",
            va="center",
            color="black",
            fontsize=8
        )
    
    if zero_duration_count > 0:
        print(f"[{instance_name}] Warning: Skipped {zero_duration_count} zero-duration task(s) in Gantt chart.")

    # Configure plot labels, grid, and title
    ax.set_yticks(range(len(machine_ids)))
    ax.set_yticklabels([f"Machine {m_id}" for m_id in machine_ids])
    
    # Format X-axis to display actual clock times (HH:MM)
    ax.xaxis.set_major_formatter(FuncFormatter(_format_time))
    ax.set_xlabel("Time of Day", fontsize=11)
    
    ax.set_ylabel("Machines", fontsize=11)
    ax.set_title(f"Gantt Chart - {instance_name}", fontsize=13, pad=15)
    ax.grid(True, linestyle="--", alpha=0.5, axis="x")

    # Build legend for Job color mapping
    legend_patches = [
        mpatches.Patch(color=job_color_map[j_id], label=f"Job {j_id}")
        for j_id in unique_jobs
    ]
    ax.legend(
        handles=legend_patches,
        title="Jobs",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        fontsize=8
    )

    # Ensure output folder exists and save plot
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Gantt chart saved to {output_path}")