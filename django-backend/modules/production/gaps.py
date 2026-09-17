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

THE BAND IS THE RUN'S OWN. A reference stone is only worth listing if it is one
that run would have accepted, so the width range comes from the seed-width band
the operator entered for the plate, not from a constant. The constants below are
the fallback for a run that states no band.

WIDTH ONLY. The band bounds the seed WIDTH — the shorter side. Length is free: a
pocket is reported whole at its true length, with `stones` saying how many it
takes. Bounding length as well was tried and reverted — it forced every pocket
into a square-ish tile, which is not how the stones are cut.

How many stones is derived from the longest seed ALREADY ON THAT PLATE, because
a length the plate demonstrably contains is a length that can be sourced. Four
attempts sit behind that one line: a fixed 13 mm cap split a 13.8 mm pocket one
stone covers; no cap at all called a 58.5 mm pocket one stone when the plate's
longest seed was 18.4 mm; and a hard length cap made every pocket a tile.

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

# THE SEED-WIDTH RANGE, and it is a hard rule rather than a target. No
# dummy/reference stone outside it is ever reported, on any plate, in the image
# or the Excel. A pocket that cannot be served by a stone in this range is left
# empty and unreported — that a gap exists is not a reason to suggest a stone
# the shop will not cut.
#
# FALLBACK seed-width range, used only when a run states no band of its own.
#
# The real range is the one the operator entered for the plate — see
# engine_runner._gap_finder, which reads P.W_LO / P.W_HI. A reference stone is
# only useful if it is a stone that run would have accepted, so the report
# follows the run rather than a constant.
#
# Width means the SHORTER side, the same measure the form bands on
# (engine_runner.seed_width = min(L, W)). LENGTH is NOT bounded: bounding it too
# forced every pocket into a square-ish tile, which the shop rejected as
# unbuildable.
#
# Expect quiet plates either way. Rim pockets are often narrower than any band a
# run would use, so many plates report no reference stones at all. That is the
# band working, not the report failing.
MIN_SEED_WIDTH = 12.0
MAX_SEED_WIDTH = 18.0

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


def _rect_pockets(placed, radius, min_width, max_width, step):
    """Empty rectangles, biggest first, each at least min_width on both sides.

    A rectangle whose SHORT side exceeds max_width is clamped to it — no stone
    may be wider than the band — and only the clamped part is consumed, so the
    strip left over stays free for the next pass instead of being thrown away.
    The LONG side is never clamped: length is not what the band bounds.
    """
    free, n = _free_grid(placed, radius, step)
    mind = max(1, int(math.ceil(min_width / step)))
    maxd = max(mind, int(math.floor(max_width / step + 1e-9)))
    out = []
    while True:
        found = _largest_rect(free, n, mind)
        if found is None:
            break
        i0, j0, wc, hc = found
        if min(wc, hc) > maxd:            # too WIDE for the band: trim the short side
            if wc <= hc:
                wc = maxd
            else:
                hc = maxd
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


def _legal(x0, y0, x1, y1, cham, radius, tree, boxes, taken, min_width,
           max_width):
    """The chamfered box as a polygon, or None if it is not a placeable stone.

    Checked exactly: the seed width inside [min_width, max_width], every vertex
    inside the usable circle (the shape is convex, so vertices inside means the
    whole piece is inside), no area shared with any placed seed, no area shared
    with a pocket already reported.
    """
    from shapely.geometry import Polygon as ShPoly

    w, h = x1 - x0, y1 - y0
    # The band constrains the seed WIDTH — the shorter side — and nothing else.
    # LENGTH is deliberately free: bounding it too forced every pocket to be a
    # square-ish 18 x 18 tile, which the shop rejected as unbuildable. A long
    # pocket is reported whole, with `stones` saying how many it takes.
    width = min(w, h)
    if width < min_width - _TOL or width > max_width + _TOL:
        return None
    if any(v < 0 for v in cham):
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


def _grow(x0, y0, x1, y1, radius, tree, boxes, taken, min_width, max_width):
    """Grow a rectangle outward, paying for the overhang with a chamfer.

    Local search. Each move extends one side and may enlarge the one or two
    chamfers on that side; a move is kept only if the result is still a legal
    stone AND covers more area than before. Chamfering costs area on its own, so
    the compound moves are what let the search trade a corner for a longer side
    rather than stopping at the first rectangle that fits.
    """
    cham = [0.0, 0.0, 0.0, 0.0]
    best = _legal(x0, y0, x1, y1, cham, radius, tree, boxes, taken,
                  min_width, max_width)
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
                           taken, min_width, max_width)
                if g is not None and g.area > best.area + 1e-6:
                    x0, y0, x1, y1, cham, best = nx0, ny0, nx1, ny1, ncham, g
                    moved = True
    return best, (x0, y0, x1, y1, tuple(round(v, 2) for v in cham))


def _cham_of(poly, bounds):
    """The 45-degree corner cuts a polygon actually has, read back off it.

    A sliced piece keeps only some of its parent's chamfers, so they cannot be
    carried over — they are measured here. For each corner of the bounding box,
    the cut is how far the outline pulls back along BOTH edges meeting there;
    equal pull-backs mean a 45-degree chamfer, which is all this module makes.
    """
    x0, y0, x1, y1 = bounds
    pts = list(poly.exterior.coords)
    out = []
    for cx, cy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        on_h = [abs(px - cx) for px, py in pts if abs(py - cy) < 1e-6]
        on_v = [abs(py - cy) for px, py in pts if abs(px - cx) < 1e-6]
        if not on_h or not on_v:
            continue
        dx, dy = min(on_h), min(on_v)
        if dx > 1e-6 and abs(dx - dy) < 1e-3:
            out.append(dx)
    return [v for v in out if v > 0]


def _slice_pocket(g, along_x, bounds, piece, n):
    """Cut a pocket polygon into `n` stones of `piece` mm along its long axis.

    Cutting the grown POLYGON, not re-tiling the raster, is what keeps the end
    stones chamfered and following the rim. Tiling the raster instead produced a
    field of identical axis-aligned squares, which is not how the rim is cut.
    """
    from shapely.geometry import box as shbox

    x0, y0, x1, y1 = bounds
    out = []
    for i in range(n):
        if along_x:
            a = x0 + i * piece
            knife = shbox(a, y0 - 1.0, a + piece, y1 + 1.0)
        else:
            a = y0 + i * piece
            knife = shbox(x0 - 1.0, a, x1 + 1.0, a + piece)
        part = g.intersection(knife)
        if part.geom_type == "Polygon" and part.area > 1e-6:
            out.append(part)
    return out


def _stone_plan(length, min_width, max_width):
    """(number of stones, length of each) for a pocket of `length`.

    No stone may be longer than max_width or shorter than min_width. Equal
    division is preferred; when no equal division satisfies both bounds the
    pocket is covered by whole max_width stones and the short remainder is left
    empty, because a remainder below the minimum is a stone nobody will cut.
    """
    if length < min_width - _TOL:
        return 0, 0.0
    n = max(1, int(math.ceil(length / max_width - 1e-9)))
    piece = length / n
    if piece >= min_width - _TOL:
        return n, piece
    n = int(math.floor(length / max_width + 1e-9))
    if n < 1:
        return 1, length
    return n, max_width


def _where(x, y, w, h, radius):
    """Plain-language position, as a fraction of the radius so it reads the same
    on a Ø90 plate and a Ø158 one."""
    cx, cy = x + w / 2.0, y + h / 2.0
    vert = ("top" if cy > radius * 0.30
            else "bottom" if cy < -radius * 0.30 else "middle")
    side = ("right" if cx > radius * 0.20
            else "left" if cx < -radius * 0.20 else "centre")
    return f"{vert}-{side}"


def gap_report(placed, radius, min_width=MIN_SEED_WIDTH,
               max_width=MAX_SEED_WIDTH, step=STEP):
    """The empty pockets on a packed plate, largest first.

    `placed` are the packed seats — dicts with x, y, w, h in mm, plate centre at
    (0, 0). `radius` is the USABLE radius, margin already removed. `min_width`
    / `max_width` bound BOTH sides of every reported stone, and both are hard.
    A pocket no stone in the range can serve is left out; one too big for a
    single stone is cut into several, each its own entry. They default to
    MIN_SEED_WIDTH / MAX_SEED_WIDTH.

    EVERY ENTRY IS ONE STONE — one row, one outline on the plate, one thing to
    buy. `stones` is therefore always 1; it and `stoneLength` are kept so the
    Excel sheet and the plate legend need no special case.

    Each entry:
        where       - plain-language position on the plate
        length      - the stone's longer side, mm (never above max_width)
        width       - the stone's shorter side, mm (this is the SEED WIDTH needed)
        stones      - always 1
        stoneLength - same as length
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

    if not placed or radius <= 0 or min_width <= 0 or max_width < min_width:
        return []

    boxes = [shbox(float(p["x"]), float(p["y"]),
                   float(p["x"]) + float(p["w"]), float(p["y"]) + float(p["h"]))
             for p in placed]
    tree = STRtree(boxes)
    taken, out = [], []
    for x, y, w, h in _rect_pockets(placed, radius, min_width, max_width, step):
        g, box = _grow(x, y, x + w, y + h, radius, tree, boxes, taken,
                       min_width, max_width)
        if g is None:
            continue
        taken.append(g)
        x0, y0, x1, y1, cham = box
        bw, bh = x1 - x0, y1 - y0
        length = max(bw, bh)
        # ONE ROW PER REAL STONE. A pocket longer than the band's maximum is cut
        # into stones that are each buildable, and each is drawn on the plate
        # separately. Reporting one 45.6 mm outline and captioning it "3 stones"
        # drew a seed that cannot exist.
        n, piece = _stone_plan(length, min_width, max_width)
        if n < 1:
            continue
        if n == 1 and piece >= length - _TOL:
            # One stone, whole pocket. Uses the EXACT chamfers the grower
            # produced rather than measuring them back off the polygon.
            out.append({
                "where": _where(x0, y0, bw, bh, radius),
                "length": round(length, 2),
                "width": round(min(bw, bh), 2),
                "stones": 1,
                "stoneLength": round(length, 2),
                "chamfer": [round(v, 2) for v in cham if v > 0],
                "area": round(g.area, 1),
                "cut": any(v >= MIN_CHAMFER for v in cham),
                "poly": [(round(px, 3), round(py, 3))
                         for px, py in g.exterior.coords],
            })
        else:
            for part in _slice_pocket(g, bw >= bh, (x0, y0, x1, y1), piece, n):
                pb = part.bounds
                pw, ph = pb[2] - pb[0], pb[3] - pb[1]
                pcham = [round(v, 2) for v in _cham_of(part, pb)]
                out.append({
                    "where": _where(pb[0], pb[1], pw, ph, radius),
                    "length": round(max(pw, ph), 2),
                    "width": round(min(pw, ph), 2),
                    "stones": 1,
                    "stoneLength": round(max(pw, ph), 2),
                    "chamfer": pcham,
                    "area": round(part.area, 1),
                    "cut": any(v >= MIN_CHAMFER for v in pcham),
                    "poly": [(round(px, 3), round(py, 3))
                             for px, py in part.exterior.coords],
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
