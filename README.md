# Multi-Objective Scheduling Optimization for Food Manufacturing

This project builds a Mixed-Integer Programming (MIP) model to solve a multi-objective scheduling problem for a food manufacturer.

Each day, a set of jobs must be processed at a station with several machines. Each job consists of a sequence of processing steps that must be completed in order, and some machines are only capable of certain step types. To make better use of limited machine capacity, some jobs may optionally be split into two pieces at a predetermined point, so that the two pieces can be scheduled on two different machines.

## Problem Formulation
### Decision Variables
All decisions are made per job (or per piece, for jobs that are split), and per machine/time as relevant.
- **Assignment** - for every job or piece, and every machine capable of running it, whether that job/piece is assigned to that machine.
- **Timing** - the start time and completion time of every job or piece on its assigned machine.
- **Sequencing** - for every pair of jobs/pieces that could be assigned to the same machine, which one is scheduled first.
- **Split** - for every job eligible to be split, whether it is actually split into two pieces.
- **Tardy** - for every job, whether it finishes after its due time.
- **Makespan** - the completion time of the schedule as a whole (the latest completion time among all jobs); a single value derived from, and constrained by, the timing variables above.

### Objective Function
The model should minimize
- **Number of Tardy Jobs** - a job is tardy if its last step (or its second piece, if split) finishes after the job's due time
- **Makespan** - the latest completion time among all jobs

The first objective always takes priority over the second: a schedule with fewer tardy jobs is preferred regardless of its makespan; makespan is only used to choose between schedules that are already tied on the number of tardy jobs.

### Constraints
- **Process order** - within a job (or a piece, if the job is split), its steps must be carried out strictly in the given order; a step cannot start until the previous step of the same job/piece has fully finished.
- **No pausing** - once a piece starts running on a machine, it must run through to completion without interruption.
- **Splitting only where allowed** - a job can only be split at its own predetermined splitting timing; a job whose splitting timing is 0 must always be scheduled as a single, uninterrupted block.
- **Limited-capability machines** - some machines can only perform a subset of process types; a job or piece may only be assigned to such a machine if every process it contains falls within that machine's allowed process types. General-purpose machines can perform any process type.
- **One machine, one job at a time** - no machine may work on two jobs/pieces at the same time; whichever job/piece is scheduled second on a machine must wait for the first one to finish.
- **Piece order for split jobs** - if a job is split, its second piece cannot start until its first piece has finished, even though the two pieces may run on different machines; a waiting gap between them is allowed even if both pieces end up on the same machine.
- **No early start** - no job or piece may start before the station opens.
- **Makespan definition** - the makespan variable must be at least as large as the completion time of every job in the schedule.
- **Tardiness definition** - the tardy variable for a job is `1` if its completion time is after its due time, and `0` otherwise.

### Solving Strategy (Multi-Objective Handling)
To strictly enforce the lexicographic priority of our two objectives (minimizing tardy jobs first, then makespan), this project implements and compares two solution approaches:

1. **Two-Stage Approach (As prescribed in the case study):**
   - **Stage 1:** The model optimizes solely for the primary objective: minimizing the total number of tardy jobs.
   - **Stage 2:** The optimal number of tardy jobs found in Stage 1 (let's call it $t$) is added to the model as a strict constraint. The model is then run a second time to minimize the makespan.

2. **Weighted Sum Approach (Single-Stage with Appropriate Positive $M$):**
   - Combined both objectives into a single objective function: `Minimize: M * (Total Tardy Jobs) + Makespan`.
   - To guarantee that reducing tardy jobs always outweighs reducing the makespan, the weight $M$ is introduced. This acts as a sufficiently large penalty that prevents the solver from trading a tardy job for a shorter makespan.

Both approaches are implemented, and their computation times and solver efficiency are compared.

### Notes and Assumptions
- A job may be split into **at most two pieces**, and only at its own predetermined splitting timing.
- A waiting gap between the two pieces of a split job is allowed, even when both pieces run on the same machine.
- Big-M for disjunctive/timing constraints is bounded by the total processing time of all steps across all jobs.
- The formulation is meant to stay general so it can be reused for future.

### Big-M Tightening Analysis and Limitations

#### 1. Findings and Performance
* **Machine Workload Impact:** Tightening Big-M using `machine_workload` primarily bounds Machine 1. Since Machines 2-5 have `All` capability, their eligible processing workload equals almost the entire system workload. Consequently, Big-M values for Machines 2-5 remain virtually identical to the un-tightened baseline, explaining why runtime speedup was marginal in benchmarks.
* **Empirical Validation:** Cross-checking the optimal 8.0h schedule against `piece_ub` in the tightened model showed **zero violations** (`Violations: False`). On this test instance, tightening did not cut off any optimal solution.

#### 2. Limitation
* `piece_ub[j,p]` is currently calculated independently for each piece based on machine eligibility without accumulating precedence delays (i.e., Piece 2 waiting for Piece 1).
* **Theoretical Risk:** If Piece 1 of a job is delayed near its upper bound, Piece 2 (if scheduled on Machine 1) must also wait, potentially increasing its actual completion time. This could invalidate the disjunctive Big-M constraint on Machine 1 and trim valid solutions.
* **Practical Assessment:** In practice, this risk is minimal because optimization objectives (minimizing makespan/tardiness) actively penalize unnecessary delays. However, while practically sound and empirically verified here, it lacks the unconditional proof of validity provided by the global baseline $N = \Pi$.

## Repo Structure

```text
.
├─ src/
│  ├─ __init__.py
│  ├─ main.py      # parse -> read -> solve -> write
│  ├─ model.py         # MILP model
│  ├─ utils.py
│  ├─ instance.py
│  └─ vis.py
│
├─ data/
│  ├─ raw/
│  │  └─ raw_data.xlsx
│  │
│  └─ processed/
│     ├─ instance_01.json
│     └─ ... 
│
├─ outputs/
│  ├─ instance_1/
│  │  ├─ instance_1_two_stage_result.json
│  │  ├─ instance_1_weighted_sum_result.json
│  │  ├─ instance_1_gantt_two_stage.png
│  │  └─ instance_1_gantt_weighted_sum.png
│  ├─ instance_2/
│  │  └─ ...
│  └─ approach_comparison.md
│
├─ requirements.txt
└─ README.md
```

## How to Run

Ensure Python 3.8+ is installed. Clone the repository and set up environment:

```bash
# Clone the repo
git clone https://github.com/tientruongminh108/iedo-scheduling-milp.git
cd iedo-scheduling-milp

# Install dependencies
pip install -r requirements.txt
```

Run the pipeline from the project root using the `-m` flag:

```bash
python -m src.main --input data/raw/raw_data.xlsx
```

By default, the pipeline parses the given Excel file, solves every sheet ("Instance 1", "Instance 2", "Instance 3", ...) it finds inside, and writes one output folder per instance under `outputs/` (e.g. `outputs/instance_1/`, containing the result JSON and Gantt chart PNG for each approach), along with the corresponding cached JSON under `data/processed/`.

If `--input` is omitted, the pipeline falls back to `data/raw/raw_data.xlsx`:

```bash
python -m src.main
```

## Author and Academic Context

This project is for Case Assignment 1 (OR110-2) in Operations Research specialization.
- **Instructor**: Prof. Ling-Chieh Kung, Department of Information Management, National Taiwan University (NTU).
- **Author**: Tien, Truong Minh
- **Email**: trnmtieen3756@gmail.com
