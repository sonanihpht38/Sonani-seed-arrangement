"""Gap report: the empty pockets left on a finished plate, and the stone that
would fill each one.

WHAT THIS IS NOT. It does not place anything. Nothing here feeds back into the
packer, changes a seat, moves a seed or alters a coverage figure — the Max
Coverage layout is frozen and was validated on a real plate, and this module is
read-only with respect to all of it. It measures what the packer left behind and
reports it, so a buyer can see what stock would close the gaps.

WHY THE GAPS EXIST. A plate is packed in rows, and a row can only open if some
stone in the pool is narrow enough to fit the chord left over. With a seed-width
band of 11-14 mm on a Ø90 plate the six rows stack to 69.4 mm inside an 80 mm
circle, and the 10.6 mm left over — a 6.6 mm strip at the top and a 4.0 mm strip
at the bottom — cannot open a row at all. That, plus the ragged ends of the
outermost rows, is the whole of the waste.

WHY THE POCKETS ARE CHAMFERED. A plain rectangle in a rim pocket is limited by
its outermost CORNER: one point stops it growing. Grinding that corner at 45
degrees lets the piece follow the curve, so the same pocket takes a noticeably
bigger stone. Every interior angle stays 90 or 135 — never below 90, which is
the shop-floor rule — and the result is a pentagon, which shapes.py already
accepts (it allows 5 to 12 corners). Measured on the reference Ø90 plate,
chamfering is worth about two millimetres of seed width: cut stones reach the
coverage plain rectangles would need stones 2 mm narrower to reach.

ONE POCKET, ONE ROW — AND AS FEW STONES AS IT REALLY TAKES. A pocket is measured
and reported whole, at its true length. How many stones fill it is a separate
number, `stones`, and it is derived from the longest seed ALREADY ON THAT PLATE
rather than any constant: a length the plate demonstrably contains is a length
that can be sourced.

This has been wrong in both directions. A fixed 13 mm cap split a 13.8 mm pocket
into two stones a single one covers. Removing the cap altogether then reported a
58.5 mm pocket on a Ø158 plate as one stone, when the longest seed on that plate
was 18.4 mm and no such stone exists. Deriving it from the plate is what makes
the answer right at both ends.

The pocket search is greedy and the chamfer search is local, so the figures are
a LOWER bound: a pocket is at least this big, never more than reported.
"""
import math

# Raster step for the empty-space scan, in mm.
#
# Do not coarsen this to "make it fast" without re-measuring. The greedy
# decomposition is sensitive to how pockets line up with the grid, so accuracy
# is NOT monotonic in the step and cannot be reasoned about from the number
# alone. Measured on the two reference plates, recoverable area was:
#
#            step 0.5      step 0.25     step 0.2
#   Ø90       377.8         372.9         393.0   mm²
#   Ø158      519.6 (6)     514.0 (6)     598.8 (8 pockets)
#
# 0.25 is WORSE than 0.5 on the Ø158 plate; 0.2 finds two whole pockets the
# others miss and is worth 15% more area. It costs 1.7 s on a Ø158 plate, next
# to roughly 90 s to pack that plate in the first place.
STEP = 0.2

# Millimetres of straight edge a chamfer must leave on each side, so the report
# never describes a stone ground away to a point.
MIN_FLAT = 1.0

# THE FLOOR. No dummy/reference stone narrower than this is ever reported, on
# any plate, in the image or the Excel. A stone below it is not something the
# shop will handle, so listing one is not a shopping tip — it is a pocket that
# cannot be filled, dressed up as one that can.
#
# What it costs, measured on the two reference plates (recoverable area with cut
# stones, and the coverage the plate would reach):
#
#            6 mm            7 mm            8 mm
#   Ø90      393 mm² 89.2%    79 mm² 83.0%     0 mm² 81.4%
#   Ø158     599 mm² 93.6%   403 mm² 92.5%   410 mm² 92.5%
#
# The Ø90 plate loses most of the benefit at 7 mm — its two big rim strips are
# 6.6 mm and 4.0 mm tall, so nothing 7 mm wide can enter them. That is the
# honest answer for that plate, not a reason to lower the floor.
MIN_SEED_WIDTH = 7.0

# A corner cut smaller than this is not a grinding operation, it is within the
# stone's own measurement tolerance. Reporting "chamfer 0.1 mm · CUT" sent a
# buyer looking for a ground stone where a plain one fits. The geometry keeps the
# exact value (it is worth 0.005 mm² of area); only the CUT/plain call uses this.
MIN_CHAMFER = 0.5

# Chamfer/extension search ladder, in mm, coarse to fine. The final 0.1 pass is
# worth ~2.5% more area on both reference plates for no measurable time.
_LADDER = (0.5, 0.25, 0.1)

_TOL = 1e-7


def _free_grid(placed, radius, step):
    """Cells wholly inside the usable circle and not covered by a seed.

    Wholly inside, not merely touching, so a pocket found here is one a stone
    really fits — the scan under-reports at the curved edge rather than over.
    """
    n = int(round(2 * radius / step))
    rsq = radius * radius
    free = [[False] * n for _ in range(n)]
    for j in range(n):
        y0 = -radius + j * step
        y1 = y0 + step
        my = max(y0 * y0, y1 * y1)
        row = free[j]
        for i in range(n):
            x0 = -radius + i * step
            x1 = x0 + step
            if max(x0 * x0, x1 * x1) + my <= rsq:
                row[i] = True
    for p in placed:
        px, py = float(p["x"]), float(p["y"])
        pw, ph = float(p["w"]), float(p["h"])
        j0 = max(0, int((py + radius) / step) - 1)
        j1 = min(n, int((py + ph + radius) / step) + 2)
        i0 = max(0, int((px + radius) / step) - 1)
        i1 = min(n, int((px + pw + radius) / step) + 2)
        for j in range(j0, j1):
            cy0 = -radius + j * step
            if cy0 + step <= py or cy0 >= py + ph:
                continue
            row = free[j]
            for i in range(i0, i1):
                cx0 = -radius + i * step
                if cx0 + step > px and cx0 < px + pw:
                    row[i] = False
    return free, n


def _largest_rect(free, n, mind):
    """Largest all-free axis-aligned rectangle with both sides >= mind cells.

    Maximal-rectangle-in-a-histogram, scanned row by row: O(n^2) overall.
    """
    best_area = 0
    best = None
    height = [0] * n
    for j in range(n):
        row = free[j]
        for i in range(n):
            height[i] = height[i] + 1 if row[i] else 0
        stack = []
        i = 0
        while i <= n:
            h = height[i] if i < n else 0
            start = i
            while stack and stack[-1][1] >= h:
                idx, hh = stack.pop()
                width = i - idx
                if hh >= mind and width >= mind and hh * width > best_area:
                    best_area = hh * width
                    best = (idx, j - hh + 1, width, hh)
                start = idx
            stack.append((start, h))
            i += 1
    return best


def _rect_pockets(placed, radius, min_width, step):
    """Empty rectangles, biggest first, each at least min_width on both sides."""
    free, n = _free_grid(placed, radius, step)
    mind = max(1, int(math.ceil(min_width / step)))
    out = []
    while True:
        found = _largest_rect(free, n, mind)
        if found is None:
            break
        i0, j0, wc, hc = found
        for jj in range(j0, j0 + hc):
            row = free[jj]
            for ii in range(i0, i0 + wc):
                row[ii] = False
        out.append((-radius + i0 * step, -radius + j0 * step, wc * step, hc * step))
    return out


def _poly(x0, y0, x1, y1, cham):
    """Corner points of a box with 45-degree chamfers cham = (bl, br, tr, tl).

    The order is fiddly and a "simplification" of it silently dropped the
    top-left point whenever its chamfer was zero, turning the shape into a
    triangle and understating every figure. test_gaps covers all sixteen
    zero/non-zero chamfer combinations for this reason.
    """
    cbl, cbr, ctr, ctl = cham
    pts = []
    if cbl:
        pts.append((x0 + cbl, y0))
    pts.append((x1 - cbr, y0))
    if cbr:
        pts.append((x1, y0 + cbr))
    else:
        pts[-1] = (x1, y0)
    pts.append((x1, y1 - ctr))
    if ctr:
        pts.append((x1 - ctr, y1))
    else:
        pts[-1] = (x1, y1)
    pts.append((x0 + ctl, y1))
    if ctl:
        pts.append((x0, y1 - ctl))
    else:
        pts[-1] = (x0, y1)
    pts.append((x0, y0 + cbl))
    if not cbl:
        pts[-1] = (x0, y0)
    return pts


def _legal(x0, y0, x1, y1, cham, radius, tree, boxes, taken, min_width):
    """The chamfered box as a polygon, or None if it is not a placeable stone.

    Checked exactly: every vertex inside the usable circle (the shape is convex,
    so vertices inside means the whole piece is inside), no area shared with any
    placed seed, no area shared with a pocket already reported.
    """
    from shapely.geometry import Polygon as ShPoly

    w, h = x1 - x0, y1 - y0
    if min(w, h) < min_width - _TOL or any(v < 0 for v in cham):
        return None
    cbl, cbr, ctr, ctl = cham
    if (cbl + cbr > w - MIN_FLAT or ctl + ctr > w - MIN_FLAT
            or cbl + ctl > h - MIN_FLAT or cbr + ctr > h - MIN_FLAT):
        return None
    g = ShPoly(_poly(x0, y0, x1, y1, cham))
    if not g.is_valid or g.area <= 0:
        return None
    rsq = radius * radius + _TOL
    for vx, vy in g.exterior.coords:
        if vx * vx + vy * vy > rsq:
            return None
    for i in tree.query(g):
        if g.intersection(boxes[i]).area > _TOL:
            return None
    for t in taken:
        if g.intersection(t).area > _TOL:
            return None
    return g


def _grow(x0, y0, x1, y1, radius, tree, boxes, taken, min_width):
    """Grow a rectangle outward, paying for the overhang with a chamfer.

    Local search. Each move extends one side and may enlarge the one or two
    chamfers on that side; a move is kept only if the result is still a legal
    stone AND covers more area than before. Chamfering costs area on its own, so
    the compound moves are what let the search trade a corner for a longer side
    rather than stopping at the first rectangle that fits.
    """
    cham = [0.0, 0.0, 0.0, 0.0]
    best = _legal(x0, y0, x1, y1, cham, radius, tree, boxes, taken, min_width)
    if best is None:
        return None, None
    for step in _LADDER:
        moved = True
        while moved:
            moved = False
            moves = []
            for delta, corners in (((0, 0, 0, step), (2, 3)),
                                   ((0, -step, 0, 0), (0, 1)),
                                   ((-step, 0, 0, 0), (0, 3)),
                                   ((0, 0, step, 0), (1, 2))):
                for use in ((), (corners[0],), (corners[1],), corners):
                    moves.append((delta, use))
            for k in range(4):
                moves.append(((0, 0, 0, 0), ("shrink", k)))
            for delta, use in moves:
                nx0, ny0 = x0 + delta[0], y0 + delta[1]
                nx1, ny1 = x1 + delta[2], y1 + delta[3]
                ncham = list(cham)
                if use and use[0] == "shrink":
                    ncham[use[1]] = max(0.0, ncham[use[1]] - step)
                else:
                    for k in use:
                        ncham[k] += step
                g = _legal(nx0, ny0, nx1, ny1, ncham, radius, tree, boxes,
                           taken, min_width)
                if g is not None and g.area > best.area + 1e-6:
                    x0, y0, x1, y1, cham, best = nx0, ny0, nx1, ny1, ncham, g
                    moved = True
    return best, (x0, y0, x1, y1, tuple(round(v, 2) for v in cham))


def _where(x, y, w, h, radius):
    """Plain-language position, as a fraction of the radius so it reads the same
    on a Ø90 plate and a Ø158 one."""
    cx, cy = x + w / 2.0, y + h / 2.0
    vert = ("top" if cy > radius * 0.30
            else "bottom" if cy < -radius * 0.30 else "middle")
    side = ("right" if cx > radius * 0.20
            else "left" if cx < -radius * 0.20 else "centre")
    return f"{vert}-{side}"


def gap_report(placed, radius, min_width=MIN_SEED_WIDTH, step=STEP):
    """The empty pockets on a packed plate, largest first.

    `placed` are the packed seats — dicts with x, y, w, h in mm, plate centre at
    (0, 0). `radius` is the USABLE radius, margin already removed. `min_width`
    is the narrowest stone the shop will accept; a pocket under it is left out.
    Defaults to MIN_SEED_WIDTH and should not be lowered past it — see the
    figures on that constant for what each setting is worth.

    Each entry:
        where       - plain-language position on the plate
        length      - the pocket's longer side, mm
        width       - the pocket's shorter side, mm (this is the SEED WIDTH needed)
        stones      - how many stones it takes, given the longest seed on this
                      plate; 1 whenever one stone can span it
        stoneLength - length of each of those stones, mm (== length when
                      stones is 1)
        chamfer     - list of 45-degree corner cuts in mm; empty means a plain
                      rectangle fits
        area        - mm² the pocket covers, chamfers already deducted
        cut         - True when a chamfer of at least MIN_CHAMFER is needed
        poly        - the pocket outline as [(x, y), ...] in mm, for drawing

    Returns [] for an empty plate or a nonsensical radius rather than raising —
    this is a report, and it must never be the reason an export fails.
    """
    from shapely.geometry import box as shbox
    from shapely.strtree import STRtree

    if not placed or radius <= 0 or min_width <= 0:
        return []

    # The longest stone this plate demonstrably holds. Anything up to it can be
    # sourced; anything beyond needs more than one stone.
    longest_seed = max(max(float(p["w"]), float(p["h"])) for p in placed)

    boxes = [shbox(float(p["x"]), float(p["y"]),
                   float(p["x"]) + float(p["w"]), float(p["y"]) + float(p["h"]))
             for p in placed]
    tree = STRtree(boxes)
    taken, out = [], []
    for x, y, w, h in _rect_pockets(placed, radius, min_width, step):
        g, box = _grow(x, y, x + w, y + h, radius, tree, boxes, taken, min_width)
        if g is None:
            continue
        taken.append(g)
        x0, y0, x1, y1, cham = box
        bw, bh = x1 - x0, y1 - y0
        length = max(bw, bh)
        stones = max(1, int(math.ceil(length / longest_seed - 1e-9)))
        out.append({
            "where": _where(x0, y0, bw, bh, radius),
            "length": round(length, 2),
            "width": round(min(bw, bh), 2),
            "stones": stones,
            "stoneLength": round(length / stones, 2),
            "chamfer": [round(v, 2) for v in cham if v > 0],
            "area": round(g.area, 1),
            "cut": any(v >= MIN_CHAMFER for v in cham),
            "poly": [(round(px, 3), round(py, 3)) for px, py in g.exterior.coords],
        })
    out.sort(key=lambda r: -r["area"])
    return out


def gap_summary(placed, radius, pockets):
    """Headline figures for the report: what is empty now and what filling the
    reported pockets would reach. Coverage here is a PROJECTION for buyers, not
    a packer result — the plate's own coverage is unchanged by this module."""
    disc = math.pi * radius * radius if radius > 0 else 0.0
    used = sum(float(p["w"]) * float(p["h"]) for p in placed) if placed else 0.0
    extra = sum(r["area"] for r in pockets)
    return {
        "usableAreaMM2": round(disc, 1),
        "coveredMM2": round(used, 1),
        "emptyMM2": round(disc - used, 1),
        "fillPct": round(100.0 * used / disc, 2) if disc else 0.0,
        "pocketCount": len(pockets),
        "recoverableMM2": round(extra, 1),
        "projectedFillPct": round(100.0 * (used + extra) / disc, 2) if disc else 0.0,
    }
