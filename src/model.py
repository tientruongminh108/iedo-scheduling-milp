"""
MILP implementation for IEDO Scheduling problem.
"""
import types

from ortools.linear_solver import pywraplp # type: ignore
from typing import Dict, Any, List
from src.instance import Instance


def _build_base_model(instance: Instance):
    """
    Build the solver, all decision variables, and all constraints EXCEPT the objective.
    Returns (solver, x, S, C, is_split, tardy, makespan, M).
    """
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        raise RuntimeError("Failed to initialize OR-Tools SCIP solver!")

    # Capability check: can machine m run this set of process types?
    def _can_do(m, proc_types):
        if not proc_types:
            return True
        return m.can_process(types.SimpleNamespace(process_types=proc_types))

    # Precompute piece durations for use in constraints
    piece_dur = {}
    for j in instance.jobs:
        piece_dur[j.id, 1] = j.get_piece_time(1)
        piece_dur[j.id, 2] = j.get_piece_time(2)

    cap = {}  # (job.id, m.id) -> (can_pre, can_post, can_full)
    for j in instance.jobs:
        pre_types = j.process_types[:j.splitting_timing] if j.can_split else j.process_types
        post_types = j.process_types[j.splitting_timing:] if j.can_split else []
        for m in instance.machines:
            cap[j.id, m.id] = (_can_do(m, pre_types), _can_do(m, post_types), _can_do(m, j.process_types))

    def _piece_ok(job_id, piece, m_id):
        can_pre, can_post, can_full = cap[job_id, m_id]
        return (can_pre or can_full) if piece == 1 else can_post

    job_pieces = []
    for j in instance.jobs:
        job_pieces.append((j.id, 1))
        if j.can_split:
            job_pieces.append((j.id, 2))

    machine_workload = {
        m.id: sum(piece_dur[jid, p] for (jid, p) in job_pieces if _piece_ok(jid, p, m.id))
        for m in instance.machines
    }

    piece_ub = {}
    for (jid, p) in job_pieces:
        eligible = [m.id for m in instance.machines if _piece_ok(jid, p, m.id)]
        piece_ub[jid, p] = max((machine_workload[mid] for mid in eligible), default=0.0)

    job_ub = {
        j.id: max(piece_ub[j.id, 1], piece_ub.get((j.id, 2), 0.0))
        for j in instance.jobs
    }
    tardy_M = {j.id: max(0.0, job_ub[j.id] - j.due_time) for j in instance.jobs}
    M = max(machine_workload.values()) if machine_workload else 0.0

    x = {}
    for j in instance.jobs:
        for p in [1, 2]:
            if p == 2 and j.splitting_timing == 0:
                continue
            for m in instance.machines:
                can_pre, can_post, can_full = cap[j.id, m.id]
                if (p == 1 and (can_pre or can_full)) or (p == 2 and can_post):
                    x[j.id, p, m.id] = solver.BoolVar(f"x_{j.id}_{p}_{m.id}")
    S = {}
    C = {}
    for j in instance.jobs:
        S[j.id, 1] = solver.NumVar(0, piece_ub[j.id, 1], f"S_{j.id}_1")
        C[j.id, 1] = solver.NumVar(0, piece_ub[j.id, 1], f"C_{j.id}_1")
        if j.can_split:
            S[j.id, 2] = solver.NumVar(0, piece_ub[j.id, 2], f"S_{j.id}_2")
            C[j.id, 2] = solver.NumVar(0, piece_ub[j.id, 2], f"C_{j.id}_2")

    # Split indicator
    is_split = {j.id: solver.BoolVar(f"is_split_{j.id}") for j in instance.jobs}

    # Tardy indicator and makespan
    tardy = {j.id: solver.BoolVar(f"tardy_{j.id}") for j in instance.jobs}
    makespan = solver.NumVar(0, M, "makespan")
    
    # Auxiliary variable to capture final completion time of each job
    C_job = {j.id: solver.NumVar(0, job_ub[j.id], f"C_job_{j.id}") for j in instance.jobs}

    jobs_by_id = {j.id: j for j in instance.jobs}

    # Per-job constraints
    for j in instance.jobs:
        if not j.can_split:
            solver.Add(is_split[j.id] == 0)

        solver.Add(solver.Sum(x[j.id, 1, m.id] for m in instance.machines if (j.id, 1, m.id) in x) == 1)

        # Piece 2 is assigned to exactly one machine iff the job is split
        if j.can_split:
            solver.Add(solver.Sum(x[j.id, 2, m.id] for m in instance.machines if (j.id, 2, m.id) in x) == is_split[j.id])

        for m in instance.machines:
            can_pre, can_post, can_full = cap[j.id, m.id]

            if (j.id, 1, m.id) in x:
                if not can_full and not can_pre:
                    solver.Add(x[j.id, 1, m.id] == 0)
                elif not can_full and can_pre:
                    # Machine can only handle the pre-split part -> job must be split to use it
                    solver.Add(x[j.id, 1, m.id] <= is_split[j.id])

            if (j.id, 2, m.id) in x:
                if not can_post:
                    solver.Add(x[j.id, 2, m.id] == 0)

        pre_time = j.get_piece_time(1)
        full_time = j.total_processing_time
        post_time = j.get_piece_time(2)

        # Piece 1 completion time
        solver.Add(
            C[j.id, 1] == S[j.id, 1] + pre_time * is_split[j.id]+ full_time * (1 - is_split[j.id])
        )
        
        # C_job must be >= C of piece 1
        solver.Add(C_job[j.id] >= C[j.id, 1])

        if j.can_split:
            # Piece 2 completion time (if split)
            solver.Add(C[j.id, 2] == S[j.id, 2] + post_time * is_split[j.id])

            # Piece 2 cannot start before piece 1 (only applies if split)
            solver.Add(S[j.id, 2] >= C[j.id, 1] - piece_ub[j.id, 1] * (1 - is_split[j.id]))

            # Isolate Piece 2 variables if job not split, to avoid makespan noise
            solver.Add(S[j.id, 2] <= piece_ub[j.id, 2] * is_split[j.id])
            solver.Add(C[j.id, 2] <= piece_ub[j.id, 2] * is_split[j.id])

            # C_job must also be >= C of piece 2
            solver.Add(C_job[j.id] >= C[j.id, 2])
            
        # Makespan definition
        solver.Add(makespan >= C_job[j.id])

        # Tardiness definition
        solver.Add(C_job[j.id] - j.due_time <= tardy_M[j.id] * tardy[j.id])

    # Symmetry breaking: within each group of identical-capability machines, force non-increasing load by machine id.
    machine_groups = {}
    for m in instance.machines:
        sig = tuple(sorted(m.capabilities))
        machine_groups.setdefault(sig, []).append(m.id)

    _load_cache = {}
    def _get_machine_load(m_id):
        """Calculate total processing workload duration assigned to machine m_id."""
        if m_id in _load_cache:
            return _load_cache[m_id]
        
        load_terms = []
        for j in instance.jobs:
            full_time = sum(j.processing_times)
            pre_time = (
                sum(j.processing_times[: j.splitting_timing])
                if j.can_split
                else full_time
            )
            post_time = full_time - pre_time

            # Load from Piece 1 (pre_time if split, full_time if unsplit)
            if (j.id, 1, m_id) in x:
                if j.can_split:
                    # Linearize: x * (pre_time * is_split + full_time * (1 - is_split))
                    # = pre_time * (x * is_split) + full_time * (x * (1 - is_split))
                    # Create auxiliary vars for x * is_split and x * (1 - is_split)
                    x_and_split = solver.BoolVar(f"x_and_split_{j.id}_1_{m_id}")
                    x_and_not_split = solver.BoolVar(f"x_and_not_split_{j.id}_1_{m_id}")
                    # x_and_split = x * is_split
                    solver.Add(x_and_split <= x[j.id, 1, m_id])
                    solver.Add(x_and_split <= is_split[j.id])
                    solver.Add(x_and_split >= x[j.id, 1, m_id] + is_split[j.id] - 1)
                    # x_and_not_split = x * (1 - is_split) = x - x_and_split
                    solver.Add(x_and_not_split <= x[j.id, 1, m_id])
                    solver.Add(x_and_not_split <= 1 - is_split[j.id])
                    solver.Add(x_and_not_split >= x[j.id, 1, m_id] - is_split[j.id])
                    # Or simpler: x_and_not_split == x - x_and_split
                    # solver.Add(x_and_not_split == x[j.id, 1, m_id] - x_and_split)
                    load_terms.append(pre_time * x_and_split + full_time * x_and_not_split)
                else:
                    # Unsplittable job: duration is always full_time
                    load_terms.append(full_time * x[j.id, 1, m_id])

            # Load from Piece 2 (active only if the job is actually split)
            if (j.id, 2, m_id) in x:
                load_terms.append(post_time * x[j.id, 2, m_id])

        expr = solver.Sum(load_terms)
        _load_cache[m_id] = expr
        return expr

    for sig, machine_ids in machine_groups.items():
        if len(machine_ids) > 1:
            machine_ids = sorted(machine_ids)
            for i in range(len(machine_ids) - 1):
                m_a = machine_ids[i]
                m_b = machine_ids[i + 1]
                solver.Add(_get_machine_load(m_a) >= _get_machine_load(m_b))

    # Valid Inequalities:
    # No overlap and Sequencing constraints
    y = {}
    for idx1, (j1, p1) in enumerate(job_pieces):
        job1 = jobs_by_id[j1]
        for (j2, p2) in job_pieces[idx1 + 1:]:
            job2 = jobs_by_id[j2]

            if j1 == j2:
                continue

            for m in instance.machines:
                if not _piece_ok(j1, p1, m.id) or not _piece_ok(j2, p2, m.id):
                    continue
                
                # Check if x variables exist for this combination
                if (j1, p1, m.id) not in x or (j2, p2, m.id) not in x:
                    continue
                
                y_var = solver.BoolVar(f"y_{j1}_{p1}_{j2}_{p2}_{m.id}")
                y[j1, p1, j2, p2, m.id] = y_var

                x1 = x[j1, p1, m.id]
                x2 = x[j2, p2, m.id]

                M_disj = machine_workload[m.id]

                solver.Add(S[j2, p2] >= C[j1, p1] - M_disj * (3 - x1 - x2 - y_var))
                solver.Add(S[j1, p1] >= C[j2, p2] - M_disj * (2 - x1 - x2 + y_var))

    return solver, x, S, C, is_split, tardy, makespan, M


def _extract_schedule(instance: Instance, x, S, is_split) -> List[Dict[str, Any]]:
    """Reads solved variable values into a plain schedule list."""
    schedule = []
    for j in instance.jobs:
        was_split = is_split[j.id].solution_value() > 0.5
        pre_time = j.get_piece_time(1)
        full_time = j.total_processing_time
        post_time = j.get_piece_time(2)

        # Piece 1 always exists
        for p in [1]:
            assigned_m = None
            for m in instance.machines:
                if (j.id, p, m.id) in x and x[j.id, p, m.id].solution_value() > 0.5:
                    assigned_m = m.id
                    break

            if assigned_m is not None:
                duration = (pre_time if was_split else full_time) if p == 1 else post_time
                schedule.append({
                    "job_id": j.id,
                    "piece": p,
                    "machine_id": assigned_m,
                    "start": S[j.id, p].solution_value(),
                    "duration": duration,
                })

        # Piece 2 only for splittable jobs that were actually split
        if j.can_split and was_split:
            p = 2
            assigned_m = None
            for m in instance.machines:
                if (j.id, p, m.id) in x and x[j.id, p, m.id].solution_value() > 0.5:
                    assigned_m = m.id
                    break

            if assigned_m is not None:
                duration = post_time
                schedule.append({
                    "job_id": j.id,
                    "piece": p,
                    "machine_id": assigned_m,
                    "start": S[j.id, p].solution_value(),
                    "duration": duration,
                })
    return schedule
 
 
def _status_name(status) -> str:
    if status == pywraplp.Solver.OPTIMAL:
        return "OPTIMAL"
    if status == pywraplp.Solver.FEASIBLE:
        return "FEASIBLE"
    return "INFEASIBLE/NO_SOLUTION_FOUND"


# Approach 1: Two-stage, exact
def solve_two_stage(instance: Instance, time_limit_ms: int = 30000) -> Dict[str, Any]:
    # Split time limit equally between the two stages for comparison with weighted-sum
    stage_time_limit = time_limit_ms // 2 if time_limit_ms is not None else None
    
    # Stage 1: minimize tardy jobs
    solver_s1, x_s1, S_s1, C_s1, is_split_s1, tardy_s1, makespan_s1, _ = _build_base_model(instance)
    obj_s1 = solver_s1.Objective()
    for j in instance.jobs:
        obj_s1.SetCoefficient(tardy_s1[j.id], 1)
    obj_s1.SetMinimization()
    if stage_time_limit is not None:
        solver_s1.set_time_limit(stage_time_limit)
    status_s1 = solver_s1.Solve()

    if status_s1 not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return {
            "approach": "two_stage",
            "status": _status_name(status_s1),
            "makespan": None,
            "tardy_jobs": None,
            "solver_time_ms": solver_s1.wall_time(),
            "schedule": [],
        }

    stage1_proven_optimal = (status_s1 == pywraplp.Solver.OPTIMAL)
    min_tardy_count = round(sum(tardy_s1[j.id].solution_value() for j in instance.jobs))

    # Stage 2: fix tardy count, minimize makespan
    solver_s2, x_s2, S_s2, C_s2, is_split_s2, tardy_s2, makespan_s2, _ = _build_base_model(instance)
    solver_s2.Add(solver_s2.Sum(tardy_s2[j.id] for j in instance.jobs) == min_tardy_count)
    obj_s2 = solver_s2.Objective()
    obj_s2.SetCoefficient(makespan_s2, 1)
    obj_s2.SetMinimization()
    if stage_time_limit is not None:
        solver_s2.set_time_limit(stage_time_limit)
    status_s2 = solver_s2.Solve()
 
    if status_s2 not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return {
            "approach": "two_stage",
            "status": _status_name(status_s2),
            "stage1_proven_optimal": stage1_proven_optimal,
            "makespan": None,
            "tardy_jobs": min_tardy_count,
            "solver_time_ms": solver_s1.wall_time() + solver_s2.wall_time(),
            "schedule": [],
        }
 
    return {
        "approach": "two_stage",
        "status": _status_name(status_s2),
        "stage1_proven_optimal": stage1_proven_optimal,
        "makespan": makespan_s2.solution_value(),
        "tardy_jobs": min_tardy_count,
        "solver_time_ms": solver_s1.wall_time() + solver_s2.wall_time(),
        "schedule": _extract_schedule(instance, x_s2, S_s2, is_split_s2),
    }
 
 
# Approach 2: Weighted-sum with a data-derived weight, single solve 
def solve_weighted_sum(instance: Instance, tardy_weight: float = None, time_limit_ms: int = 30000) -> Dict[str, Any]:
    solver, x, S, C, is_split, tardy, makespan, M = _build_base_model(instance)
    
    default_weight = M + 1
    W = tardy_weight if tardy_weight is not None else default_weight
 
    objective = solver.Objective()
    for j in instance.jobs:
        objective.SetCoefficient(tardy[j.id], W)
    objective.SetCoefficient(makespan, 1)
    objective.SetMinimization()
    if time_limit_ms is not None:
        solver.set_time_limit(time_limit_ms)
    status = solver.Solve()
 
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return {
            "approach": "weighted_sum",
            "status": _status_name(status),
            "makespan": None,
            "tardy_jobs": None,
            "solver_time_ms": solver.wall_time(),
            "schedule": [],
            "tardy_weight_used": W,
        }
 
    return {
        "approach": "weighted_sum",
        "status": _status_name(status),
        "makespan": makespan.solution_value(),
        "tardy_jobs": round(sum(tardy[j.id].solution_value() for j in instance.jobs)),
        "solver_time_ms": solver.wall_time(),
        "schedule": _extract_schedule(instance, x, S, is_split),
        "tardy_weight_used": W,
    }
 
 
# Entry point: run one or more approaches 
def solve_instance(
    instance: Instance, approach: str = "both", time_limit_ms: int = 300000
) -> Dict[str, Any]:
    valid = ("two_stage", "weighted_sum", "both")
    if approach not in valid:
        raise ValueError(
            f"Unknown approach '{approach}'; expected one of {valid}."
        )

    if approach == "two_stage":
        return solve_two_stage(instance, time_limit_ms=time_limit_ms)

    if approach == "weighted_sum":
        return solve_weighted_sum(instance, time_limit_ms=time_limit_ms)

    two_stage_result = solve_two_stage(instance, time_limit_ms=time_limit_ms)
    weighted_result = solve_weighted_sum(instance, time_limit_ms=time_limit_ms)

    tardy_counts_match = (
        two_stage_result.get("tardy_jobs") is not None
        and two_stage_result.get("tardy_jobs") == weighted_result.get("tardy_jobs")
    )
    makespans_match = (
        two_stage_result.get("makespan") is not None
        and weighted_result.get("makespan") is not None
        and abs(two_stage_result["makespan"] - weighted_result["makespan"]) < 1e-4
    )

    res = dict(two_stage_result)
    res.update({
        "instance_name": instance.name,
        "two_stage": two_stage_result,
        "weighted_sum": weighted_result,
        "tardy_counts_match": tardy_counts_match,
        "makespans_match": makespans_match,
        "results_match": tardy_counts_match and makespans_match,
    })

    return res