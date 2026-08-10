"""
CP-SAT implementation for IEDO Scheduling problem.
"""
import types
from typing import Dict, Any, List

from ortools.sat.python import cp_model
from src.instance import Instance

SCALE = 10  # data has at most 1 decimal place


def _can_do(m, proc_types):
    if not proc_types:
        return True
    return m.can_process(types.SimpleNamespace(process_types=proc_types))


def _build_base_model(instance: Instance):
    """Build the CP-SAT model, all decision variables, and all constraints EXCEPT the objective."""
    model = cp_model.CpModel()

    piece_dur = {}
    for j in instance.jobs:
        piece_dur[j.id, 1] = round(j.get_piece_time(1) * SCALE)
        piece_dur[j.id, 2] = round(j.get_piece_time(2) * SCALE)

    cap = {}
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
        piece_ub[jid, p] = max((machine_workload[mid] for mid in eligible), default=0)

    job_ub = {
        j.id: max(piece_ub[j.id, 1], piece_ub.get((j.id, 2), 0))
        for j in instance.jobs
    }
    tardy_M = {j.id: max(0, job_ub[j.id] - round(j.due_time * SCALE)) for j in instance.jobs}
    horizon = max(machine_workload.values()) if machine_workload else 0

    jobs_by_id = {j.id: j for j in instance.jobs}

    # Assignment vars
    x = {}
    for (jid, p) in job_pieces:
        for m in instance.machines:
            if _piece_ok(jid, p, m.id):
                x[jid, p, m.id] = model.new_bool_var(f"x_{jid}_{p}_{m.id}")

    # Split indicator
    is_split = {j.id: model.new_bool_var(f"is_split_{j.id}") for j in instance.jobs}
    for j in instance.jobs:
        if not j.can_split:
            model.add(is_split[j.id] == 0)

    # Start/end vars per piece
    S = {}
    C = {}
    for j in instance.jobs:
        S[j.id, 1] = model.new_int_var(0, piece_ub[j.id, 1], f"S_{j.id}_1")
        C[j.id, 1] = model.new_int_var(0, piece_ub[j.id, 1], f"C_{j.id}_1")
        if j.can_split:
            S[j.id, 2] = model.new_int_var(0, piece_ub[j.id, 2], f"S_{j.id}_2")
            C[j.id, 2] = model.new_int_var(0, piece_ub[j.id, 2], f"C_{j.id}_2")

    # Optional interval vars per (piece, machine)
    intervals_by_machine: Dict[int, List] = {m.id: [] for m in instance.machines}
    for (jid, p) in job_pieces:
        job = jobs_by_id[jid]
        pre_time = piece_dur[jid, 1]
        full_time = piece_dur[jid, 1] + piece_dur.get((jid, 2), 0)
        for m in instance.machines:
            if (jid, p, m.id) not in x:
                continue
            # Duration on this machine depends on is_split
            if p == 1:
                dur_var = model.new_int_var(0, piece_ub[jid, 1], f"dur_{jid}_1_{m.id}")
                # dur_var = pre_time * is_split + full_time * (1 - is_split)
                model.add(dur_var == pre_time).OnlyEnforceIf([x[jid, 1, m.id], is_split[jid]])
                model.add(dur_var == full_time).OnlyEnforceIf([x[jid, 1, m.id], is_split[jid].Not()])
            else:
                dur_var = model.new_int_var(0, piece_ub[jid, 2], f"dur_{jid}_2_{m.id}")
                model.add(dur_var == piece_dur[jid, 2]).OnlyEnforceIf(x[jid, 2, m.id])

            interval = model.new_optional_interval_var(
                S[jid, p], dur_var, C[jid, p], x[jid, p, m.id], f"iv_{jid}_{p}_{m.id}"
            )
            intervals_by_machine[m.id].append(interval)

    for m in instance.machines:
        if intervals_by_machine[m.id]:
            model.add_no_overlap(intervals_by_machine[m.id])

    # Tardy / makespan
    tardy = {j.id: model.new_bool_var(f"tardy_{j.id}") for j in instance.jobs}
    makespan = model.new_int_var(0, horizon, "makespan")
    C_job = {j.id: model.new_int_var(0, job_ub[j.id], f"C_job_{j.id}") for j in instance.jobs}

    for j in instance.jobs:
        pre_time = piece_dur[j.id, 1]
        full_time = piece_dur[j.id, 1] + piece_dur.get((j.id, 2), 0)
        post_time = piece_dur.get((j.id, 2), 0)

        # Piece 1 assigned to exactly one eligible machine
        model.add(sum(x[j.id, 1, m.id] for m in instance.machines if (j.id, 1, m.id) in x) == 1)

        if j.can_split:
            # Piece 2 assigned iff job is split
            model.add(sum(x[j.id, 2, m.id] for m in instance.machines if (j.id, 2, m.id) in x) == is_split[j.id])

        for m in instance.machines:
            can_pre, can_post, can_full = cap[j.id, m.id]
            if (j.id, 1, m.id) in x and not can_full and can_pre:
                model.add(x[j.id, 1, m.id] <= is_split[j.id])

        # Piece 1 completion time
        model.add(C[j.id, 1] == S[j.id, 1] + pre_time).OnlyEnforceIf(is_split[j.id])
        model.add(C[j.id, 1] == S[j.id, 1] + full_time).OnlyEnforceIf(is_split[j.id].Not())

        model.add(C_job[j.id] >= C[j.id, 1])

        if j.can_split:
            model.add(C[j.id, 2] == S[j.id, 2] + post_time).OnlyEnforceIf(is_split[j.id])
            # Piece 2 cannot start before piece 1 finishes, only meaningful if split
            model.add(S[j.id, 2] >= C[j.id, 1]).OnlyEnforceIf(is_split[j.id])
            # Isolate piece-2 vars when not split (keeps them at 0, mirrors SCIP model)
            model.add(S[j.id, 2] == 0).OnlyEnforceIf(is_split[j.id].Not())
            model.add(C[j.id, 2] == 0).OnlyEnforceIf(is_split[j.id].Not())

            model.add(C_job[j.id] >= C[j.id, 2])

        model.add(makespan >= C_job[j.id])

        # Tardiness
        due = round(j.due_time * SCALE)
        model.add(C_job[j.id] - due <= tardy_M[j.id] * tardy[j.id])

    # Symmetry breaking: within each group of identical-capability machines, force non-increasing load by machine id
    machine_groups = {}
    for m in instance.machines:
        sig = tuple(sorted(m.capabilities))
        machine_groups.setdefault(sig, []).append(m.id)

    def _machine_load_expr(m_id):
        terms = []
        for (jid, p) in job_pieces:
            if (jid, p, m_id) not in x:
                continue
            if p == 1:
                full_time = piece_dur[jid, 1] + piece_dur.get((jid, 2), 0)
                pre_time = piece_dur[jid, 1]
                # Load contribution: x * (pre_time if split else full_time).
                terms.append(pre_time * x[jid, p, m_id])
                terms.append((full_time - pre_time) * x[jid, p, m_id])
            else:
                terms.append(piece_dur[jid, 2] * x[jid, p, m_id])
        return sum(terms) if terms else 0

    for sig, machine_ids in machine_groups.items():
        if len(machine_ids) > 1:
            machine_ids = sorted(machine_ids)
            for i in range(len(machine_ids) - 1):
                model.add(_machine_load_expr(machine_ids[i]) >= _machine_load_expr(machine_ids[i + 1]))

    return {
        "model": model,
        "x": x,
        "S": S,
        "C": C,
        "is_split": is_split,
        "tardy": tardy,
        "makespan": makespan,
        "C_job": C_job,
        "job_pieces": job_pieces,
    }


def _extract_schedule(instance: Instance, solver, x, S, is_split) -> List[Dict[str, Any]]:
    schedule = []
    for j in instance.jobs:
        was_split = solver.Value(is_split[j.id]) > 0
        pre_time = j.get_piece_time(1)
        full_time = j.total_processing_time
        post_time = j.get_piece_time(2)

        assigned_m = None
        for m in instance.machines:
            if (j.id, 1, m.id) in x and solver.Value(x[j.id, 1, m.id]) > 0:
                assigned_m = m.id
                break
        if assigned_m is not None:
            duration = pre_time if was_split else full_time
            schedule.append({
                "job_id": j.id, "piece": 1, "machine_id": assigned_m,
                "start": solver.Value(S[j.id, 1]) / SCALE,
                "duration": duration,
            })

        if j.can_split and was_split:
            assigned_m = None
            for m in instance.machines:
                if (j.id, 2, m.id) in x and solver.Value(x[j.id, 2, m.id]) > 0:
                    assigned_m = m.id
                    break
            if assigned_m is not None:
                schedule.append({
                    "job_id": j.id, "piece": 2, "machine_id": assigned_m,
                    "start": solver.Value(S[j.id, 2]) / SCALE,
                    "duration": post_time,
                })
    return schedule


def _status_name(status) -> str:
    if status == cp_model.OPTIMAL:
        return "OPTIMAL"
    if status == cp_model.FEASIBLE:
        return "FEASIBLE"
    return "INFEASIBLE/NO_SOLUTION_FOUND"


def solve_cpsat(instance: Instance, time_limit_ms: int = 30000, num_search_workers: int = None) -> Dict[str, Any]:
    stage_time_limit_s = (time_limit_ms / 2 / 1000) if time_limit_ms is not None else None

    # Stage 1: minimize tardy jobs
    b1 = _build_base_model(instance)
    b1["model"].Minimize(sum(b1["tardy"][j.id] for j in instance.jobs))

    solver1 = cp_model.CpSolver()
    if stage_time_limit_s is not None:
        solver1.parameters.max_time_in_seconds = stage_time_limit_s
    if num_search_workers is not None:
        solver1.parameters.num_search_workers = num_search_workers
    status1 = solver1.Solve(b1["model"])

    if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "approach": "cpsat",
            "status": _status_name(status1),
            "makespan": None,
            "tardy_jobs": None,
            "solver_time_ms": solver1.WallTime() * 1000,
            "schedule": [],
        }

    stage1_proven_optimal = (status1 == cp_model.OPTIMAL)
    min_tardy_count = round(sum(solver1.Value(b1["tardy"][j.id]) for j in instance.jobs))

    # Stage 2: fix tardy count, minimize makespan
    b2 = _build_base_model(instance)
    b2["model"].add(sum(b2["tardy"][j.id] for j in instance.jobs) == min_tardy_count)
    b2["model"].Minimize(b2["makespan"])

    solver2 = cp_model.CpSolver()
    if stage_time_limit_s is not None:
        solver2.parameters.max_time_in_seconds = stage_time_limit_s
    if num_search_workers is not None:
        solver2.parameters.num_search_workers = num_search_workers
    status2 = solver2.Solve(b2["model"])

    if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "approach": "cpsat",
            "status": _status_name(status2),
            "stage1_proven_optimal": stage1_proven_optimal,
            "makespan": None,
            "tardy_jobs": min_tardy_count,
            "solver_time_ms": (solver1.WallTime() + solver2.WallTime()) * 1000,
            "schedule": [],
        }

    return {
        "approach": "cpsat",
        "status": _status_name(status2),
        "stage1_proven_optimal": stage1_proven_optimal,
        "makespan": solver2.Value(b2["makespan"]) / SCALE,
        "tardy_jobs": min_tardy_count,
        "solver_time_ms": (solver1.WallTime() + solver2.WallTime()) * 1000,
        "schedule": _extract_schedule(instance, solver2, b2["x"], b2["S"], b2["is_split"]),
    }