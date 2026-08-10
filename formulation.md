# Formal Formulation for IEDO Scheduling Problem

## Sets and Parameters
- $I$: set of jobs, indexed by $i, j \in I$
- $M$: set of machines, indexed by $m \in M$
- $S = \{1, 2\}$: piece index of a job, indexed by $s, t \in S$. Piece 1 is either the whole job (if it is not split) or the portion before its predetermined split point (if it is split). Piece 2 only exists if the job is actually split, and is the portion from the split point onward.
- $M^I \subseteq M$: machines with limited process capability (e.g. Machine 1, which can only perform Boiling)
- $M^C = M \setminus M^I$: general-purpose machines, able to perform every process type
- $k_i \ge 0$: job $i$'s predetermined splitting timing ($k_i = 0$ means job $i$ cannot be split at all)
- $I^{split} = \{ i \in I : k_i > 0 \}$: jobs that are *eligible* to be split (splitting is optional even for these jobs)
- $P_i^{pre}$: total processing time of job $i$'s processes before its split point (equals job $i$'s full processing time if $k_i = 0$)
- $P_i^{post}$: total processing time of job $i$'s processes from its split point onward (equals 0 if $k_i = 0$)
- $P_i^{full} = P_i^{pre} + P_i^{post}$: total processing time of job $i$ if run as a single, unsplit block
- $D_i$: due time of job $i$
- $B_i^m \in \{0,1\}$, for $i \in I^{split}, m \in M^I$: 1 if limited machine $m$ can process every process type contained in job $i$'s **pre**-split portion
- $G_i^m \in \{0,1\}$, for $i \in I^{split}, m \in M^I$: 1 if limited machine $m$ can process every process type contained in job $i$'s **post**-split portion
- $F_i^m \in \{0,1\}$, for $i \in I, m \in M^I$: 1 if limited machine $m$ can process every process type in job $i$'s **full**, unsplit set of processes
- $N_1, N_2, N_3$: sufficiently large positive numbers (Big-M constants; see derivation below)

**Why not just one fixed $P_{is}$ and $C_{is}$ per phase, as in a simpler write-up?** Because splitting is a *decision*, not a given: whether piece 1 has duration $P_i^{pre}$ or $P_i^{full}$, and whether a limited machine is eligible for piece 1 at all, both depend on whether the job actually ends up split. The parameters above ($B_i^m$, $F_i^m$, $G_i^m$, $P_i^{pre}$, $P_i^{post}$, $P_i^{full}$) are fixed data computed from the instance, but they are combined with the **decision variable** $\delta_i$ below rather than collapsed into a single fixed $P_{is}$/$C_{is}$ ahead of time.

## Decision Variables
- $\delta_i \in \{0,1\}$, for $i \in I^{split}$: 1 if job $i$ is actually split into two pieces, 0 if it is kept as one block. (For $i \notin I^{split}$, $\delta_i$ is fixed at 0 rather than a free variable, since those jobs cannot split.)
- $x_{i1} \ge 0$: the completion time of job $i$'s piece 1 - always defined
- $x_{i2} \ge 0$, for $i \in I^{split}$: the completion time of job $i$'s piece 2 - only meaningful when $\delta_i = 1$; pinned to 0 otherwise (Constraint 3)
- $C_i \ge 0$: the **overall** completion time of job $i$ (its last-finished piece)
- $y_{i1m} \in \{0,1\}$, for $i \in I, m \in M$: 1 if piece 1 of job $i$ is assigned to machine $m$
- $y_{i2m} \in \{0,1\}$, for $i \in I^{split}, m \in M$: 1 if piece 2 of job $i$ is assigned to machine $m$
- $z_{isjt} \in \{0,1\}$: 1 if piece $s$ of job $i$ is scheduled before piece $t$ of job $j$ on a machine they could share, 0 otherwise
- $e_i \in \{0,1\}$: 1 if job $i$ is tardy, 0 otherwise
- $w \ge 0$: the makespan

## Constraints

### 1. Machine Assignment
$$ \sum_{m \in M} y_{i1m} = 1 \quad \forall i \in I $$
$$ \sum_{m \in M} y_{i2m} = \delta_i \quad \forall i \in I^{split} $$

Piece 1 of every job is assigned to exactly one machine. Piece 2 is assigned to exactly one machine **if and only if** the job is actually split - if $\delta_i = 0$, no machine is assigned to a (non-existent) piece 2.

### 2. Machine Capability Restrictions (for $m \in M^I$)
$$ y_{i1m} \le B_i^m\,\delta_i + F_i^m\,(1 - \delta_i) \quad \forall i \in I^{split} $$
$$ y_{i1m} \le F_i^m \quad \forall i \in I \setminus I^{split} $$
$$ y_{i2m} \le G_i^m \quad \forall i \in I^{split} $$

This is the key mechanic that governs when a limited machine (Machine 1) may be used. A limited machine may take piece 1 only if **either** (a) the job is genuinely split and piece 1's own processes fit the machine's capability, **or** (b) the job is run whole and the machine can handle *every* process in it. In practice, for Machine 1 this means: an unsplit multi-process job can never use Machine 1; a job can only route its Boiling-only portion there once it is actually split. No restriction applies for $m \in M^C$.

### 3. Piece Duration and Sequencing
$$ x_{i1} \ge P_i^{pre}\,\delta_i + P_i^{full}\,(1-\delta_i) \quad \forall i \in I $$

(For $i \notin I^{split}$, $\delta_i \equiv 0$, so this reduces to $x_{i1} \ge P_i^{full}$.)

$$ x_{i2} \ge x_{i1} + P_i^{post} - N_3(1 - \delta_i) \quad \forall i \in I^{split} $$
$$ x_{i2} \le N_3\,\delta_i \quad \forall i \in I^{split} $$

The first inequality enforces "piece 2 cannot start before piece 1 finishes" only when the job is actually split ($\delta_i = 1$); the Big-M term relaxes it otherwise. The second inequality pins $x_{i2} = 0$ whenever the job is not split, keeping the unused piece out of the way of every other constraint. Note there is no requirement that pieces 1 and 2 land on *different* machines - a gap between them is allowed even if both are assigned to the same machine.

### 4. Job Completion Time
$$ C_i \ge x_{i1} \quad \forall i \in I $$
$$ C_i \ge x_{i2} \quad \forall i \in I^{split} $$

$C_i$ is the job's true completion time - the later of its two pieces if split, or simply $x_{i1}$ if not.

### 5. Machine Disjunctive Constraints
For every pair of pieces $(i,s)$ and $(j,t)$ that could feasibly be assigned to the same machine $m$ (with $i < j$, $s, t \in \{1, 2\}$, restricted to pieces that actually exist for their job):

$$
x_{is} + P_{jt} - x_{jt} \le N_1 \left[ (1 - z_{isjt}) + (2 - y_{ism} - y_{jtm}) \right]
$$

$$
x_{jt} + P_{is} - x_{is} \le N_1 \left[ z_{isjt} + (2 - y_{ism} - y_{jtm}) \right]
$$

where $P_{is}$ denotes the duration actually realized for piece $s$ of job $i$ under Constraint 3 (i.e. $P_i^{pre}$ or $P_i^{full}$ for $s=1$ depending on $\delta_i$; $P_i^{post}$ for $s=2$). Pairs where $i = j$ (the two pieces of the *same* job) are excluded - their relative order is already fixed by Constraint 3, and forcing them apart would incorrectly forbid scheduling both pieces on the same machine.

### 6. Tardiness Constraints
$$ C_i \le D_i + N_2\, e_i \quad \forall i \in I $$

## Stage 1: Minimize the total number of tardy jobs
$$ \text{Minimize } \sum_{i \in I} e_i $$

Subject to Constraints 1-6, with

$$ x_{i1}, x_{i2}, C_i \ge 0,\quad y_{ism}, z_{isjt}, e_i, \delta_i \in \{0,1\} $$

## Stage 2: Minimize Makespan
After deriving the minimum number of tardy jobs, say $T^*$, add a constraint restricting the number of tardy jobs to $T^*$ and minimize the makespan $w$.

$$ \text{Minimize } w $$

Subject to Constraints 1-6, plus

$$ \sum_{i \in I} e_i = T^* $$
$$ w \ge C_i \quad \forall i \in I $$
$$ w \ge 0 $$

## Big-$N$ Parameters
A simple, always-valid (if loose) choice, using the instance's total workload $\Pi = \sum_{i \in I} P_i^{full}$:

$$ N_1 \ge \Pi \qquad N_2 \ge \Pi \qquad N_3 \ge \Pi $$

**Note on Machine-Specific Big-M Tightening:** Bounding $N_1$ locally per machine/piece (e.g., using maximum workload of eligible pieces per machine) reduces solver search space for limited machines (such as Machine 1). While empirically valid for tested instances, this tightening assumes piece completion times do not exceed independent machine workloads. For guaranteed theoretical validity across arbitrary precedence delays, the global bound $N = \Pi$ remains the strictly proven baseline.