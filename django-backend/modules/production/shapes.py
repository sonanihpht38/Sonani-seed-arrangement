# ===================== DOMAIN LAYER: seed outline geometry =====================
# Irregular seeds (Max Coverage only).
#
# A seed row may carry an optional CORNER LIST describing its true outline, for
# seeds that are not a plain Length x Width rectangle — typically a rectangular
# blank with one or more corners cut off. Everything here is pure geometry: no
# Django, no database, no I/O, so it can be unit-tested in isolation and reused
# unchanged by the image-based detector (which emits the same corner list).
#
# GOVERNING RULE — a seed whose corner list fails validation is STILL IMPORTED,
# as today's Length x Width rectangle. Bad shape data must never cost you the
# seed; it only costs you the extra packing accuracy. Callers surface the
# returned reason as a warning, they do not abort the import.
#
# WHY THE CORNER COUNT STARTS AT 5: the interior angles of a simple n-gon sum to
# (n-2)*180. For n=4 that is 360, so a quadrilateral with every angle >= 90 must
# have all four angles exactly 90 — it IS a rectangle. Since these seeds are
# guaranteed >= 90 at every corner, a genuinely irregular outline necessarily has
# 5 or more corners, and a 4-corner list means the data is wrong.

import math

# ---- Validation limits (tune here; every rule below reads these) -------------
MIN_CORNERS = 5           # see note above: <5 with all angles >=90 is a rectangle
MAX_CORNERS = 12          # beyond this the outline is noise, not a cut blank
MIN_ANGLE_DEG = 85.0      # seeds are >=90 by nature (manufacturing); +/-5 deg
                          # measuring tolerance, so 85 is the practical floor
MAX_ANGLE_DEG = 180.0     # above this the corner is reflex (outline caves in)
BBOX_TOL = 0.05           # corner list must span L x W within 5%
MIN_AREA_RATIO = 0.50     # area must be at least half its own bounding box
MIN_EDGE_MM = 0.5         # no hairline slivers
COORD_DP = 3              # stored precision (micron); measurements are 2dp


def parse_corners(raw):
    """'x,y; x,y; ...' -> [(x, y), ...] in mm, or None if it cannot be read.

    Forgiving about whitespace and about a trailing repeat of the first point
    (the format says don't close the ring, but closing it is a harmless habit).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    pts = []
    for part in text.replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        bits = part.split(",")
        if len(bits) != 2:
            return None
        try:
            pts.append((float(bits[0]), float(bits[1])))
        except (TypeError, ValueError):
            return None
    if len(pts) >= 2 and _same(pts[0], pts[-1]):
        pts.pop()                       # ring closed explicitly — drop the repeat
    return pts or None


def _same(a, b, eps=1e-9):
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def signed_area(pts):
    """Shoelace. Positive = counter-clockwise, negative = clockwise."""
    n = len(pts)
    return sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
               for i in range(n)) / 2.0


def polygon_area(pts):
    return abs(signed_area(pts))


def interior_angles(pts):
    """Interior angle at each vertex, in degrees, in the order given.

    Orientation-aware: the interior of a counter-clockwise ring is on the other
    side from a clockwise one, so the turn is measured the opposite way round.
    Getting this backwards silently yields the EXTERIOR angles (270 where 90 is
    right), which then fails every rule — hence the sum test in the unit tests.
    """
    n = len(pts)
    ccw = signed_area(pts) > 0
    out = []
    for i in range(n):
        ax, ay = pts[i - 1]                 # previous (wraps at i=0)
        bx, by = pts[i]                     # this vertex
        cx, cy = pts[(i + 1) % n]           # next
        a1 = math.atan2(ay - by, ax - bx)   # b -> previous
        a2 = math.atan2(cy - by, cx - bx)   # b -> next
        d = (a1 - a2) if ccw else (a2 - a1)
        out.append(math.degrees(d) % 360.0)
    return out


def edge_lengths(pts):
    n = len(pts)
    return [math.dist(pts[i], pts[(i + 1) % n]) for i in range(n)]


def bounding_box(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _is_simple(pts):
    """True when the outline does not cross itself. shapely is already a hard
    dependency of the packing engine; imported lazily to keep this module cheap
    to import from the request path."""
    try:
        from shapely.geometry import Polygon as ShPoly
    except ImportError:                     # geometry lib absent -> skip the check
        return True
    try:
        return bool(ShPoly(pts).is_valid)
    except Exception:
        return False


def validate_corners(raw, length, width):
    """Validate a seed's corner list against its measured Length x Width.

    Returns ``(coords, reason)``:
      * ``(coords, None)``  — valid. ``coords`` is re-origined so the outline's
        bottom-left sits at (0, 0), rounded to COORD_DP, ready to store.
      * ``(None, None)``    — no corner data. Not an error: use the rectangle.
      * ``(None, reason)``  — invalid. Use the rectangle AND report ``reason``.

    The bounding-box rule is the important one. Every other check asks "is this
    a sane shape?"; only this one asks "is this shape THIS seed's?" — which is
    what catches a corner list pasted onto the wrong row, the failure mode that
    otherwise looks entirely plausible and quietly corrupts a plate.
    """
    if raw is None or str(raw).strip() == "":
        return None, None                   # blank is the normal case, not a fault

    pts = parse_corners(raw)
    if pts is None:
        return None, "corner list could not be read (expected 'x,y; x,y; ...')"

    n = len(pts)
    if n < MIN_CORNERS:
        return None, (
            "%d corners — an irregular seed needs at least %d "
            "(a 4-corner shape with every angle >= 90 is a rectangle)"
            % (n, MIN_CORNERS))
    if n > MAX_CORNERS:
        return None, "%d corners — more than the %d allowed" % (n, MAX_CORNERS)

    if polygon_area(pts) <= 0:
        return None, "corners are collinear or repeated (zero area)"

    if not _is_simple(pts):
        return None, "outline crosses itself"

    short = min(edge_lengths(pts))
    if short < MIN_EDGE_MM:
        return None, "shortest side %.2f mm is below the %.2f mm minimum" % (short, MIN_EDGE_MM)

    angles = interior_angles(pts)
    worst = min(angles)
    if worst < MIN_ANGLE_DEG:
        return None, "corner angle %.1f deg is below the %.0f deg minimum" % (worst, MIN_ANGLE_DEG)
    widest = max(angles)
    if widest > MAX_ANGLE_DEG:
        return None, "corner angle %.1f deg is reflex — the outline caves inward" % widest

    try:
        L = float(length)
        W = float(width)
    except (TypeError, ValueError):
        return None, "Length/Width missing, so the corner list cannot be checked"
    if L <= 0 or W <= 0:
        return None, "Length/Width must be greater than zero"

    _, _, bw, bh = bounding_box(pts)
    if abs(bw - L) > BBOX_TOL * L or abs(bh - W) > BBOX_TOL * W:
        return None, (
            "outline spans %.2f x %.2f mm but the row says %.2f x %.2f "
            "(over %.0f%% out — is it on the right row?)"
            % (bw, bh, L, W, BBOX_TOL * 100))

    area = polygon_area(pts)
    nominal = L * W
    if area < MIN_AREA_RATIO * nominal:
        return None, ("area %.2f mm2 is under %.0f%% of the %.2f mm2 bounding box"
                      % (area, MIN_AREA_RATIO * 100, nominal))
    if area > nominal * 1.001:              # 0.1% for floating point
        return None, ("area %.2f mm2 exceeds its own %.2f mm2 bounding box"
                      % (area, nominal))

    x0, y0, _, _ = bounding_box(pts)
    coords = [(round(x - x0, COORD_DP), round(y - y0, COORD_DP)) for x, y in pts]
    return coords, None


# ---- Reconstruction from edge measurements ----------------------------------
# Seeds are measured by hand as FOUR AXIS-PARALLEL EDGES, walking the outline:
#
#       L1 = bottom      W2 = right      L3 = top      W4 = left
#
# A blank with a corner ground off has one shortened edge on each axis, so the
# pair (longer, shorter) on each axis gives both the bounding box and the cut:
#
#       Length = max(L1, L3)      cut along x = |L1 - L3|
#       Width  = max(W2, W4)      cut along y = |W2 - W4|
#
# and the cut sits at the corner the two SHORTENED edges share. That is why no
# diagonal or angle is needed: the outline is a rectangle with one straight
# corner cut, which these four numbers pin down completely. The result always
# has angles of 90, 90, 90 and two obtuse — consistent with the >=90 rule.
CUT_EPS = 0.05            # mm — below this an edge pair counts as "not cut"


def corners_from_sides(l1, w2, l3, w4):
    """Four edge lengths -> ``[(x, y), ...]``, or None if they cannot be read.

    ``l1`` bottom, ``w2`` right, ``l3`` top, ``w4`` left, in mm. The outline is
    returned with its bottom-left at (0, 0), ready for validate_corners().

    A pair that matches within CUT_EPS means that axis is uncut; if both match
    the seed is a plain rectangle and this returns its four corners, which
    validate_corners() will then reject as "not irregular" — correctly, because
    a rectangle needs no outline stored.
    """
    try:
        l1, w2, l3, w4 = float(l1), float(w2), float(l3), float(w4)
    except (TypeError, ValueError):
        return None
    if min(l1, w2, l3, w4) <= 0:
        return None

    L, W = max(l1, l3), max(w2, w4)
    p, q = abs(l1 - l3), abs(w2 - w4)      # cut legs along x and along y
    if p <= CUT_EPS and q <= CUT_EPS:
        return [(0.0, 0.0), (L, 0.0), (L, W), (0.0, W)]     # no cut: a rectangle
    if p >= L or q >= W:
        return None                        # a cut cannot consume a whole edge

    # The cut corner is where the two SHORTENED edges meet.
    top_short, right_short = l3 < l1, w2 < w4
    if top_short and right_short:                      # top-right
        pts = [(0, 0), (L, 0), (L, W - q), (L - p, W), (0, W)]
    elif top_short and not right_short:                # top-left
        pts = [(0, 0), (L, 0), (L, W), (p, W), (0, W - q)]
    elif right_short:                                  # bottom-right
        pts = [(p, 0), (L, 0), (L, W), (0, W), (0, q)]
    else:                                              # bottom-left
        pts = [(0, q), (p, 0), (L, 0), (L, W), (0, W)]
    return [(round(float(x), COORD_DP), round(float(y), COORD_DP)) for x, y in pts]


def sides_to_corners(l1, w2, l3, w4):
    """corners_from_sides() + validation, in one call.

    Returns ``(coords, reason)`` exactly like validate_corners(), so the import
    path treats an edge-measured seed and a corner-listed one identically.
    """
    pts = corners_from_sides(l1, w2, l3, w4)
    if pts is None:
        return None, "side measurements could not be read"
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    raw = "; ".join("%g,%g" % p for p in pts)
    return validate_corners(raw, max(xs) - min(xs), max(ys) - min(ys))


# ---- Placement (Max Coverage only) ------------------------------------------
# Angles tried when fitting a stone into a seat. Upright first, so an outline
# that already suits the seat is never needlessly rotated.
FIT_ANGLES = (0, 90, 180, 270)
FIT_EPS = 1e-6            # shapely contains() is exact; give the boundary a hair


def fit_polygon_in_seat(pts, seat, angles=FIT_ANGLES):
    """Place a stone outline entirely inside `seat`, or report that it cannot.

    ``pts``  — the stone's outline in its own coordinates (origin at its
               bottom-left), as stored in TRN_SeedData.CornersJSON.
    ``seat`` — a shapely Polygon in plate coordinates: the region the Max
               Coverage row grid carved out and is about to hand a stone.

    Returns the placed outline as ``[(x, y), ...]`` in plate coordinates, or
    ``None`` when the stone does not fit in any tried orientation.

    WHY THIS EXISTS: the row grid sizes its seats from the MEDIAN seed width and
    height, then assigns a stone without checking it. For rectangles that is a
    safe approximation. For an irregular outline it is not — a cut corner can
    make a stone that "measures" 12.4 x 9.8 unable to occupy a 12.4 x 9.8 seat in
    the orientation the row wants. Testing the fit is what turns the measured
    outline into real accuracy instead of a stored-but-ignored field.

    Containment is REQUIRED — the stone is never trimmed to make it fit. Cutting
    a seed is a physical step, so an engine that shrank a stone in software would
    report coverage it has not earned. A stone that does not fit is simply not
    placed here: accuracy first, coverage second.

    Deliberately a SMALL candidate search, not a nesting solver: a handful of
    right-angle rotations against a few alignments. Seeds are convex with >= 90
    corners and seats are convex-ish, so this finds a fit when one plausibly
    exists, and costs nothing when the stone has no outline (callers skip it).
    """
    if not pts or seat is None or seat.is_empty:
        return None
    from shapely import affinity
    from shapely.geometry import Polygon as ShPoly

    stone = ShPoly(pts)
    if not stone.is_valid:
        stone = stone.buffer(0)
    if stone.is_empty or stone.area <= 0:
        return None
    # Cheap reject before any rotation maths.
    if stone.area > seat.area + FIT_EPS:
        return None

    sx0, sy0, sx1, sy1 = seat.bounds
    for deg in angles:
        cand = affinity.rotate(stone, deg, origin="centroid") if deg else stone
        bx0, by0, bx1, by1 = cand.bounds
        if (bx1 - bx0) > (sx1 - sx0) + FIT_EPS or (by1 - by0) > (sy1 - sy0) + FIT_EPS:
            continue                      # bounding box alone rules this angle out
        # Alignments worth trying: each corner of the seat's bounding box, then
        # centroid-on-centroid. Corner-first mirrors how the row grid packs —
        # flush into a corner rather than floating in the middle.
        targets = (
            (sx0 - bx0, sy0 - by0),
            (sx1 - bx1, sy0 - by0),
            (sx0 - bx0, sy1 - by1),
            (sx1 - bx1, sy1 - by1),
            (seat.centroid.x - cand.centroid.x, seat.centroid.y - cand.centroid.y),
        )
        for dx, dy in targets:
            moved = affinity.translate(cand, dx, dy)
            if seat.contains(moved) or seat.buffer(FIT_EPS).contains(moved):
                return [(round(x, COORD_DP), round(y, COORD_DP))
                        for x, y in moved.exterior.coords]
    return None
