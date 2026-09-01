"""Run the Max Coverage sweep's independent packs across CPU cores.

WHY THIS EXISTS. `enhanced_plate_job` packs the plate once per combination of
(fill direction x seat score x cut policy x row phase) and keeps the best — 20
packs on the shipped settings. Every one of those packs is a pure function of
its arguments: `_pack_once` draws nothing, writes no module state and shares
nothing with its siblings. They are therefore embarrassingly parallel, and the
sweep is essentially the whole cost of generating a plate.

This is the ONLY kind of speed-up that leaves the result untouched. The same
packs are run, scored by the same rule, and the same winner is chosen — the work
is merely spread over more cores. Nothing here changes which plate comes out.

WORKER GLOBALS. `_pack_once` reads its settings from module globals (P.R,
P.CLEARANCE, P.T_LO, the tunables in demo_fill). A forked worker inherits them,
but a SPAWNED one — which is what Windows does, and what Python 3.14 does
everywhere — starts from a freshly imported module holding defaults. Packing
would then silently run at Ø87 with a 0.67-0.73 thickness gate whatever the user
asked for. `snapshot_globals()` captures them in the parent and every worker
restores them before packing, so a spawned worker is configured identically to
the parent rather than merely importable.
"""

# The engine settings a pack depends on. Anything a worker must agree with the
# parent about belongs here; a value missing from this list is a silent
# wrong-answer bug on a spawned worker, not a crash, so keep it complete.
_PACK_GLOBALS = (
    "PLATE_D", "USABLE_D", "R", "S2", "INSCRIBED",
    "T_LO", "T_HI", "GRID", "CLEARANCE", "MINSEED", "W_LO", "W_HI",
)

_TUNABLES = (
    "ENHANCED_ANGLES", "NEST_STEP", "ROW_PROBE", "RIM_EPS", "ROW_TOL",
    "SWEEP_ANCHORS", "ROW_LEVEL_TOL", "LEVEL_BAND", "LEVEL_MARGIN", "LEVEL_TRIES",
    "CUT_POLICIES", "FILL_DIRECTIONS", "ROW_PHASES", "ROW_PHASE_REFINE",
    "SEAT_SCORES", "RIM_FLUSH", "CUTS_FIRST", "CENTRE_BAND", "CUT_NOTCH_MAX",
    "CUT_BONUS", "RECONSIDER", "RECONSIDER_ROUNDS", "SWEEP_ROW_TOL",
    "ROW_END_STEP", "ROW_END_ROUNDS", "ROW_END_NEST", "ROW_END_LIFTS",
    "ROW_END_CUT_GAP", "ROW_END_MIN_HEIGHT_FRAC", "CENTRE_SIZE_BIAS",
    "CUT_OUTWARD_MIN", "RESIDUAL_FILL", "SIZE_GRADIENT_FRAC",
)


def snapshot_globals():
    """Capture the packing settings the parent is configured with."""
    import demo_fill as D
    import pack_v2 as P

    return (
        {k: getattr(P, k, None) for k in _PACK_GLOBALS},
        {k: getattr(D, k, None) for k in _TUNABLES},
    )


def restore_globals(snap):
    """Apply a parent's settings inside a worker process."""
    import demo_fill as D
    import pack_v2 as P

    pack, tune = snap
    for k, v in pack.items():
        if v is not None or k in ("W_LO", "W_HI"):
            setattr(P, k, v)
    for k, v in tune.items():
        if v is not None:
            setattr(D, k, v)


def run_one(task):
    """One pack, in a worker. Top-level and picklable so spawn can reach it.

    `task` is ((args, snapshot), (y0, policy, direction, seat)).
    """
    import os
    import sys

    os.environ.setdefault("MPLBACKEND", "Agg")
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:            # demo_fill imports pack_v2 by bare name
        sys.path.insert(0, here)

    (args, snap), (y0, policy, direction, seat) = task
    restore_globals(snap)

    import demo_fill as D
    return D._pack_once(args, y0, policy, direction, seat)


# Below this many stones a pack is quick enough that spawning workers costs more
# than it saves — process start-up on Windows is a fresh interpreter plus a
# shapely import per worker. The unit tests pack a handful of synthetic seeds and
# must not pay for a pool.
MIN_STONES_FOR_PARALLEL = 40


def run_packs(args, jobs, max_workers=None):
    """Run `jobs` (each a (y0, policy, direction, seat) tuple) and return the
    results IN THE ORDER GIVEN.

    Order is part of the contract, not a convenience: the caller keeps the first
    result that strictly beats the running best, so ties are settled by position.
    Returning them out of order would silently change which plate ships.

    Falls back to running them in-process on any failure. The most likely one is
    a Celery prefork worker, whose processes are daemonic and are not allowed to
    have children — there the sweep simply runs as it always did.
    """
    real = args[0]
    if len(jobs) < 2 or len(real) < MIN_STONES_FOR_PARALLEL:
        return [_seq_one(args, j) for j in jobs]

    try:
        import os
        from concurrent.futures import ProcessPoolExecutor

        # PACK_WORKERS caps the pool. It matters when more than one arrangement
        # job runs at once: without it two concurrent jobs would each open a
        # pool the width of the machine and thrash. Set it to
        # cores / worker-concurrency in a deployment that runs several.
        cap = os.environ.get("PACK_WORKERS")
        limit = int(cap) if (cap or "").strip().isdigit() else (os.cpu_count() or 2)
        workers = max_workers or max(1, min(len(jobs), limit))
        payload = (args, snapshot_globals())
        with ProcessPoolExecutor(max_workers=workers) as ex:
            # .map preserves input order.
            return list(ex.map(run_one, [(payload, j) for j in jobs]))
    except Exception:                    # noqa: BLE001 - any pool failure degrades
        return [_seq_one(args, j) for j in jobs]


def _seq_one(args, job):
    import demo_fill as D

    y0, policy, direction, seat = job
    return D._pack_once(args, y0, policy, direction, seat)
