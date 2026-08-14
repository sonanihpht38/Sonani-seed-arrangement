r"""
DEMO max-fill (saved separately).

1. Take the REAL eligible seeds (thickness + shape gated) from the datasheet.
2. Arrange them into inscribed-square plates with MaxRects best-fit + 90 deg
   rotation (checks all blocks, not in sheet order).
3. Fill every remaining gap with DEMO filler seeds (>= 2x2 mm, square/rectangular)
   using an EXACT rectilinear decomposition of the empty space (cut at the real
   seeds' own edges -> no grid-resolution loss). This drives plate-fill toward 100%.
4. Save to a SEPARATE place: images_demofill\  +  arrangement_demofill.xlsx.

Demo fillers are synthetic (NOT from the datasheet) and clearly marked.

Usage:  .\venv\Scripts\python.exe demo_fill.py [FILE] [--plate 90 --margin 3
                                       --t-lo 0.67 --t-hi 0.73 --shape all --min-seed 2]
"""
import os, glob, math, argparse
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Circle, Rectangle as Rect, Patch, Polygon as MplPoly
from matplotlib.collections import PatchCollection
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
import pack_v2 as P


def free_rectangles_circle(placed, R, min_seed):
    """Rectangle cover of the empty area across the WHOLE Ø(2R) usable circle (not
    just the inscribed square). Cuts the grid at the placed seeds' edges AND on a
    fine uniform grid, so the curved-boundary regions and the staircase notches the
    rows leave get captured instead of dropped wholesale. A cell is fillable only
    when empty AND fully inside the circle, so merged filler rects (both sides >=
    min_seed) stay inside the edge. Returns rects in plate-centered coords."""
    step = max(0.5, min(1.0, min_seed / 2.0))
    xs = {-R, R}; ys = {-R, R}
    k = 1
    while -R + k * step < R:                              # fine uniform grid lines
        v = round(-R + k * step, 3); xs.add(v); ys.add(v); k += 1
    for p in placed:                                      # plus exact seed edges
        xs.add(p["x"]); xs.add(p["x"] + p["w"]); ys.add(p["y"]); ys.add(p["y"] + p["h"])
    xs = sorted(v for v in xs if -R - 1e-9 <= v <= R + 1e-9)
    ys = sorted(v for v in ys if -R - 1e-9 <= v <= R + 1e-9)
    nx, ny = len(xs) - 1, len(ys) - 1
    if nx <= 0 or ny <= 0:
        return []
    R2 = R * R
    free = [[False] * nx for _ in range(ny)]
    for j in range(ny):
        y0, y1 = ys[j], ys[j + 1]; my = max(y0 * y0, y1 * y1)
        for i in range(nx):
            x0, x1 = xs[i], xs[i + 1]
            if max(x0 * x0, x1 * x1) + my > R2 + 1e-9:
                continue                                  # cell crosses the circle edge -> skip
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            covered = any(p["x"] - 1e-9 <= cx <= p["x"] + p["w"] + 1e-9 and
                          p["y"] - 1e-9 <= cy <= p["y"] + p["h"] + 1e-9 for p in placed)
            free[j][i] = not covered
    used = [[False] * nx for _ in range(ny)]
    rects = []
    for j in range(ny):
        for i in range(nx):
            if not free[j][i] or used[j][i]:
                continue
            i2 = i
            while i2 < nx and free[j][i2] and not used[j][i2]:
                i2 += 1
            j2 = j
            while j2 < ny and all(free[j2][k2] and not used[j2][k2] for k2 in range(i, i2)):
                j2 += 1
            for jj in range(j, j2):
                for ii in range(i, i2):
                    used[jj][ii] = True
            w, h = xs[i2] - xs[i], ys[j2] - ys[j]
            if w >= min_seed and h >= min_seed:
                rects.append((xs[i], ys[j], w, h))
    return rects


def dummy_fill_2mm(placed, R, size=2.0, step=0.5):
    """Flood-fill every empty space inside the Ø(2R) usable circle with FIXED
    size×size dummy seeds (default 2×2 mm), packed greedily bottom-left. A dummy is
    placed only where the whole square is inside the circle and overlaps no real seed
    or already-placed dummy (conservative cell-intersection test -> never overlaps a
    real seed). Returns a list of (x, y) lower-left corners. Aggressively fills the
    perimeter / curved-boundary gaps down to the 2 mm granularity."""
    n = int(round(2 * R / step))
    R2 = R * R
    cov = [[False] * n for _ in range(n)]
    for p in placed:                                      # mark every cell the seed touches
        i0 = max(0, int((p["x"] + R) / step) - 1)
        i1 = min(n, int((p["x"] + p["w"] + R) / step) + 2)
        j0 = max(0, int((p["y"] + R) / step) - 1)
        j1 = min(n, int((p["y"] + p["h"] + R) / step) + 2)
        for j in range(j0, j1):
            cy0 = -R + j * step; cy1 = cy0 + step
            if cy1 <= p["y"] or cy0 >= p["y"] + p["h"]:
                continue
            row = cov[j]
            for i in range(i0, i1):
                cx0 = -R + i * step
                if cx0 + step > p["x"] and cx0 < p["x"] + p["w"]:
                    row[i] = True
    d = int(round(size / step))                           # fine cells per dummy side
    dummies = []
    for j in range(n - d + 1):
        y = -R + j * step
        my = max(y * y, (y + size) * (y + size))
        for i in range(n - d + 1):
            x = -R + i * step
            if max(x * x, (x + size) * (x + size)) + my > R2 + 1e-9:
                continue                                  # 2×2 not fully inside the circle
            ok = True
            for dj in range(d):
                row = cov[j + dj]
                for di in range(d):
                    if row[i + di]:
                        ok = False; break
                if not ok:
                    break
            if ok:
                dummies.append((x, y))
                for dj in range(d):
                    row = cov[j + dj]
                    for di in range(d):
                        row[i + di] = True
    return dummies


def cluster_dummies(dummies, size=2.0, link=2.2):
    """Group 2×2 dummy seeds into connected clusters (union-find; centres within
    `link` mm = edge-adjacent). Returns dicts: count, cx/cy (centroid), x0/y0/x1/y1
    (bbox), sorted largest-first. Used for the report / Excel cluster listing."""
    n = len(dummies)
    if n == 0:
        return []
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a

    cen = [(x + size / 2, y + size / 2) for (x, y) in dummies]
    link2 = link * link
    bucket = {}
    for idx, (cx, cy) in enumerate(cen):
        bucket.setdefault((round(cx / 2), round(cy / 2)), []).append(idx)
    for idx, (cx, cy) in enumerate(cen):
        bx, by = round(cx / 2), round(cy / 2)
        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                for jdx in bucket.get((bx + ddx, by + ddy), ()):
                    if jdx <= idx:
                        continue
                    dx = cx - cen[jdx][0]; dy = cy - cen[jdx][1]
                    if dx * dx + dy * dy <= link2:
                        parent[find(idx)] = find(jdx)
    groups = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(idx)
    out = []
    for members in groups.values():
        xs = [cen[m][0] for m in members]; ys = [cen[m][1] for m in members]
        out.append({"count": len(members), "cx": sum(xs) / len(xs), "cy": sum(ys) / len(ys),
                    "x0": min(dummies[m][0] for m in members),
                    "y0": min(dummies[m][1] for m in members),
                    "x1": max(dummies[m][0] + size for m in members),
                    "y1": max(dummies[m][1] + size for m in members)})
    out.sort(key=lambda c: -c["count"])
    return out


def _largest_rect(free, n, mind):
    """Largest all-free axis-aligned rectangle in the n×n grid `free` with BOTH sides
    >= mind cells. Returns (i0, j0, wc, hc) or None. Histogram + stack, O(n^2)."""
    best_area = 0
    best = None
    height = [0] * n
    for j in range(n):
        row = free[j]
        for i in range(n):
            height[i] = height[i] + 1 if row[i] else 0
        stack = []                                        # (start_index, bar_height)
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


def hybrid_fill(placed, R, min_size=2.0, step=1.0):
    """Gap fill, LARGEST-FIRST: build the free-cell grid inside the usable circle
    (cells fully inside and not covered by a real seed), then repeatedly place the
    single biggest empty rectangle as a BIG filler seed until none larger than
    min_size×min_size remains; finally drop fixed min_size square DUMMY seeds into
    whatever small/curved cells are left. Covering big areas with big seeds first
    sharply cuts the dummy count. Returns (big_fillers, small_dummies):
    big = (x, y, w, h) list, small = (x, y) lower-left corners (min_size square)."""
    n = int(round(2 * R / step))
    R2 = R * R
    mind = max(1, int(round(min_size / step)))
    free = [[False] * n for _ in range(n)]
    for j in range(n):                                    # cells fully inside the circle
        y0 = -R + j * step; y1 = y0 + step; my = max(y0 * y0, y1 * y1)
        rowf = free[j]
        for i in range(n):
            x0 = -R + i * step; x1 = x0 + step
            if max(x0 * x0, x1 * x1) + my <= R2 + 1e-9:
                rowf[i] = True
    for p in placed:                                      # subtract real-seed coverage
        i0 = max(0, int((p["x"] + R) / step) - 1); i1 = min(n, int((p["x"] + p["w"] + R) / step) + 2)
        j0 = max(0, int((p["y"] + R) / step) - 1); j1 = min(n, int((p["y"] + p["h"] + R) / step) + 2)
        for j in range(j0, j1):
            cy0 = -R + j * step; cy1 = cy0 + step
            if cy1 <= p["y"] or cy0 >= p["y"] + p["h"]:
                continue
            rowf = free[j]
            for i in range(i0, i1):
                cx0 = -R + i * step
                if cx0 + step > p["x"] and cx0 < p["x"] + p["w"]:
                    rowf[i] = False
    big = []                                              # PASS 1: largest rectangle first
    while True:
        r = _largest_rect(free, n, mind)
        if r is None:
            break
        i0, j0, wc, hc = r
        if wc <= mind and hc <= mind:
            break                                         # nothing bigger than a dummy left
        for jj in range(j0, j0 + hc):
            rowf = free[jj]
            for ii in range(i0, i0 + wc):
                rowf[ii] = False
        big.append((-R + i0 * step, -R + j0 * step, wc * step, hc * step))
    small = []                                            # PASS 2: 2×2 dummies into the rest
    d = mind
    for j in range(n - d + 1):
        for i in range(n - d + 1):
            ok = True
            for dj in range(d):
                rowf = free[j + dj]
                for di in range(d):
                    if not rowf[i + di]:
                        ok = False; break
                if not ok:
                    break
            if ok:
                small.append((-R + i * step, -R + j * step))
                for dj in range(d):
                    rowf = free[j + dj]
                    for di in range(d):
                        rowf[i + di] = False
    return big, small


def _free_grid(placed, R, step):
    """Boolean n×n grid: True = cell fully inside the usable circle AND not covered
    by a real seed (conservative). Shared by hybrid_fill and cross_fill."""
    n = int(round(2 * R / step)); R2 = R * R
    free = [[False] * n for _ in range(n)]
    for j in range(n):
        y0 = -R + j * step; y1 = y0 + step; my = max(y0 * y0, y1 * y1)
        rowf = free[j]
        for i in range(n):
            x0 = -R + i * step; x1 = x0 + step
            if max(x0 * x0, x1 * x1) + my <= R2 + 1e-9:
                rowf[i] = True
    for p in placed:
        i0 = max(0, int((p["x"] + R) / step) - 1); i1 = min(n, int((p["x"] + p["w"] + R) / step) + 2)
        j0 = max(0, int((p["y"] + R) / step) - 1); j1 = min(n, int((p["y"] + p["h"] + R) / step) + 2)
        for j in range(j0, j1):
            cy0 = -R + j * step; cy1 = cy0 + step
            if cy1 <= p["y"] or cy0 >= p["y"] + p["h"]:
                continue
            rowf = free[j]
            for i in range(i0, i1):
                cx0 = -R + i * step
                if cx0 + step > p["x"] and cx0 < p["x"] + p["w"]:
                    rowf[i] = False
    return free, n


def _in_tri(di, dj, s, orient):
    """Is cell (di,dj) inside the right-triangle of leg s, by right-angle corner."""
    if orient == 0:                       # right angle bottom-left
        return di + dj <= s - 1
    if orient == 1:                       # right angle bottom-right
        return dj <= di
    if orient == 2:                       # right angle top-left
        return di <= dj
    return di + dj >= s - 1                # right angle top-right


def _grow_tri(free, n, i0, j0, orient):
    """Largest right-triangle (equal legs s) of orientation `orient` anchored with its
    box bottom-left at cell (i0,j0): grow s while every triangle cell is free."""
    s = 0
    while i0 + s + 1 <= n and j0 + s + 1 <= n:
        s1 = s + 1
        ok = True
        for dj in range(s1):
            row = free[j0 + dj]
            for di in range(s1):
                if _in_tri(di, dj, s1, orient) and not row[i0 + di]:
                    ok = False
                    break
            if not ok:
                break
        if not ok:
            break
        s = s1
    return s


def _tri_verts(i0, j0, s, orient, R, step):
    """The 3 (x,y) corners of the right-triangle (plate-centered coords)."""
    def pt(ci, cj):
        return (-R + ci * step, -R + cj * step)
    if orient == 0:
        return [pt(i0, j0), pt(i0 + s, j0), pt(i0, j0 + s)]
    if orient == 1:
        return [pt(i0, j0), pt(i0 + s, j0), pt(i0 + s, j0 + s)]
    if orient == 2:
        return [pt(i0, j0), pt(i0, j0 + s), pt(i0 + s, j0 + s)]
    return [pt(i0 + s, j0), pt(i0 + s, j0 + s), pt(i0, j0 + s)]


def cross_fill(placed, R, min_size=2.0, step=0.5):
    """Gap fill, LARGEST-SUITABLE-SHAPE first, all fillers >= min_size (client minimum
    seed). Dummy shapes = triangle + square + rectangle (no plus/cross). PASS A big
    rectangles (the large interior gaps between seed rows); PASS B1 right-TRIANGLE seeds
    placed FIRST in every diagonal/curved notch (one triangle replaces a staircase of
    small squares); PASS C square/rectangle fillers down to min_size for the rest.
    Returns (big, crosses, tris, fine): big=(x,y,w,h); crosses=[] (kept for signature);
    tris=([3 (x,y) verts], area); fine=(x,y,w,h)."""
    free, n = _free_grid(placed, R, step)
    aw = max(1, int(round(min_size / step)))

    def block_free(i, j, wc, hc):
        for jj in range(j, j + hc):
            rowf = free[jj]
            for ii in range(i, i + wc):
                if not rowf[ii]:
                    return False
        return True

    big_min = 2 * aw                                      # only chunky rects (>=2*min_size both sides)
    big = []                                              # PASS A: big rectangles
    while True:
        r = _largest_rect(free, n, big_min)               # leaves thin boundary strips for crosses
        if r is None:
            break
        i0, j0, wc, hc = r
        for jj in range(j0, j0 + hc):
            rowf = free[jj]
            for ii in range(i0, i0 + wc):
                rowf[ii] = False
        big.append((-R + i0 * step, -R + j0 * step, wc * step, hc * step))

    tris = []                                             # PASS B1: right-triangle seeds
    min_tri = 2 * aw                                          # legs >= 2*min_size; only GENUINELY
    for j in range(n):                                    # triangular gaps (a full square wouldn't fit)
        rowf = free[j]
        for i in range(n):
            if not rowf[i]:
                continue
            bs = bo = 0
            for orient in range(4):
                s = _grow_tri(free, n, i, j, orient)
                if s > bs:
                    bs, bo = s, orient
            if bs >= min_tri and not block_free(i, j, bs, bs):
                for dj in range(bs):
                    fr = free[j + dj]
                    for di in range(bs):
                        if _in_tri(di, dj, bs, bo):
                            fr[i + di] = False
                tris.append((_tri_verts(i, j, bs, bo, R, step), bs * bs / 2.0 * step * step))

    crosses = []                                          # cross/plus seeds removed: the requested
    #                                                       dummy shapes are triangle + square +
    #                                                       rectangle only; triangles (above) are
    #                                                       placed BEFORE the square/rect fill below.
    fine = []                                             # PASS C: square / rectangle fillers >= min_size
    while True:                                           # (client minimum seed = min_size×min_size)
        r = _largest_rect(free, n, aw)                    # largest-first, both sides >= min_size
        if r is None:
            break
        i0, j0, wc, hc = r
        for jj in range(j0, j0 + hc):
            rowf = free[jj]
            for ii in range(i0, i0 + wc):
                rowf[ii] = False
        fine.append((-R + i0 * step, -R + j0 * step, wc * step, hc * step))
    return big, crosses, tris, fine


def irregular_fill(seeds, R, min_irr=1.5, cell=25.0):
    """Fill EVERY gap (the whole free region = usable circle minus the `seeds`) with
    IRREGULAR POLYGONS instead of many square/rectangle dummies — far fewer, larger
    seeds. Shapely:
      1. free = circle(coarse 24-gon, so outer edges are STRAIGHT cuts not a faux-curve)
         minus union(seeds).
      2. OPEN the WHOLE free region ONCE (erode min_irr/2, dilate back) -> drops the
         <min_irr-thick crescent but stays FLUSH with the seeds. (Opening AFTER the grid
         cut would shave a strip off every cut edge -> thin slivers/gaps between seeds &
         dummies — the bug this fixes.)
      3. Grid-cut the OPENED region so no single piece wraps the whole boundary; cut
         pieces TILE (share the cut line) -> no gaps.
      4. Any piece a grid line clipped thinner than min_irr is MERGED into the neighbour
         it shares the most edge with -> no sub-min_irr dummy AND no gap.
    Returns [(exterior [(x,y)...], area, (label_x, label_y))]."""
    from shapely.geometry import Point, Polygon as ShPoly, box
    from shapely.ops import unary_union
    occ = [ShPoly([(p["x"], p["y"]), (p["x"] + p["w"], p["y"]),
                   (p["x"] + p["w"], p["y"] + p["h"]), (p["x"], p["y"] + p["h"])]) for p in seeds]
    free = Point(0, 0).buffer(R, resolution=6).difference(unary_union(occ))
    rad = min_irr / 2.0
    opened = free.buffer(-rad, join_style=2).buffer(rad, join_style=2)
    if opened.is_empty:
        return []
    grid = []
    k = -R
    while k < R:
        grid.append(k); k += cell
    pieces = []
    for yy in grid:
        for xx in grid:
            pc = opened.intersection(box(xx, yy, xx + cell, yy + cell))
            if pc.is_empty:
                continue
            for g in (pc.geoms if pc.geom_type in ("MultiPolygon", "GeometryCollection") else [pc]):
                if getattr(g, "geom_type", "") == "Polygon" and not g.is_empty and g.area >= min_irr * min_irr * 0.4:
                    pieces.append(g)
    good = [p for p in pieces if not p.buffer(-rad).is_empty]    # >= min_irr thick somewhere
    thin = [p for p in pieces if p.buffer(-rad).is_empty]        # grid-clipped slivers
    for t in thin:                                               # fold each sliver into its best neighbour
        bi, bl = -1, 0.0
        tb = t.buffer(0.05)
        for i, gp in enumerate(good):
            a = tb.intersection(gp).area
            if a > bl:
                bl, bi = a, i
        if bi >= 0:
            m = unary_union([good[bi], t])
            if m.geom_type == "Polygon":
                good[bi] = m
    out = []
    for h in good:
        h = h.simplify(0.5)                                      # straight edges; merge near-collinear
        if not h.is_valid:
            h = h.buffer(0)
        if h.is_empty or h.geom_type != "Polygon" or h.area < min_irr * min_irr * 0.6:
            continue
        rp = h.representative_point()                            # a point GUARANTEED inside (label)
        out.append(([(round(x, 3), round(y, 3)) for x, y in h.exterior.coords],
                    h.area, (round(rp.x, 3), round(rp.y, 3))))
    return out


def hull_fill(real, R, min_irr=1.5, n_circ=12):
    """IMAGE-PATTERN dummies (reference image): a few BIG corner triangles + edge/cap
    triangles that fill the whole band out to the circle, each a SEPARATE cuttable piece.
    Construction matching the reference: take the convex hull of (seed-cluster corners +
    `n_circ` points spaced on the circle) — this hull CUTS each circle-corner with a
    straight diagonal -> the big corner triangles; subtract the seeds -> the gap pieces
    (corners, caps, sides); fan-triangulate each gap piece into separate triangles. All
    straight edges, reaches the circle, ~96% fill. Returns
    [(exterior [(x,y)...], area, (label_x, label_y))]."""
    from shapely.geometry import Point, Polygon as ShPoly, MultiPoint
    from shapely.ops import unary_union, triangulate
    seeds = [ShPoly([(p["x"], p["y"]), (p["x"] + p["w"], p["y"]),
                     (p["x"] + p["w"], p["y"] + p["h"]), (p["x"], p["y"] + p["h"])]) for p in real]
    su = unary_union(seeds)
    cpts = [(R * math.cos(2 * math.pi * k / n_circ), R * math.sin(2 * math.pi * k / n_circ))
            for k in range(n_circ)]
    cc = [c for g in (su.geoms if su.geom_type == "MultiPolygon" else [su])
          for c in list(g.exterior.coords)[:-1]]
    hull = MultiPoint(cc + cpts).convex_hull               # corner-cutting outer outline
    region = hull.difference(su)                           # the gap pieces (corners/caps/sides)
    rad = min_irr / 2.0
    out = []
    for pc in (region.geoms if region.geom_type == "MultiPolygon" else [region]):
        if pc.is_empty or pc.geom_type != "Polygon" or pc.area < min_irr * min_irr:
            continue
        for t in triangulate(MultiPoint(list(pc.exterior.coords)[:-1])):   # fan into SEPARATE triangles
            ti = t.intersection(pc)
            for g in (ti.geoms if ti.geom_type in ("MultiPolygon", "GeometryCollection") else [ti]):
                if g.geom_type != "Polygon" or g.is_empty or g.area < min_irr * min_irr * 0.8:
                    continue
                if g.buffer(-rad).is_empty:               # drop sub-min_irr-thick slivers
                    continue
                g = g.simplify(0.3)
                if not g.is_valid:
                    g = g.buffer(0)
                if g.is_empty or g.geom_type != "Polygon":
                    continue
                rp = g.representative_point()
                out.append(([(round(x, 3), round(y, 3)) for x, y in g.exterior.coords],
                            g.area, (round(rp.x, 3), round(rp.y, 3))))
    return out


def guillotine_tri_fill(real, R, min_size, sub_h=2.0, cap_h=2.0, v_inset=1.5, n_cham=1, max_bands=2):
    """MACHINE-CUT dummies shaped like the client's GREEN reference: a RECTANGLE whose curved-
    boundary corner is cut by ONE single straight CHAMFER (a clean convex pentagon), so EVERY
    corner is >= 90 deg (no acute corners, no fine staircase, no multi-segment faux-curve).
    Trick: at the WIDE end of a side gap the outer edge starts with a short VERTICAL segment
    (`v_inset` mm) so it meets the horizontal cap at 90 deg; then ONE straight diagonal
    (n_cham=1) runs to the narrow end. Applied symmetrically to the left/right side gaps.
    The TOP/BOTTOM CAPS are kept as plain axis-aligned RECTANGLES (client: caps must stay
    rectangular/square, not irregular). Returns [(ring, area, (lx,ly))]."""
    from shapely.geometry import Polygon as ShPoly

    def cx(y):
        return math.sqrt(max(0.0, R * R - y * y))

    def outer_chain(y0, y1):
        """Outer boundary points (x>0 side) from y0 up to y1 that meet horizontal caps at
        >= 90 deg: a vertical inset at any WIDE end, then chamfers following the circle."""
        eps = 0.3
        pts = []
        # bottom end
        if cx(y0) > cx(min(y0 + eps, y1)):                # bottom is the wide end -> vertical inset
            yv = min(y0 + v_inset, (y0 + y1) / 2.0)
            pts += [(cx(yv), y0), (cx(yv), yv)]
            lo = yv
        else:                                             # bottom narrow -> reach the circle
            pts.append((cx(y0), y0))
            lo = y0
        # top end
        if cx(y1) > cx(max(y1 - eps, y0)):                # top is the wide end -> vertical inset
            yv2 = max(y1 - v_inset, (y0 + y1) / 2.0)
            top = [(cx(yv2), yv2), (cx(yv2), y1)]
            hi = yv2
        else:
            top = [(cx(y1), y1)]
            hi = y1
        if hi - lo > 0.5:                                 # chamfers along the curve
            for i in range(1, n_cham):
                t = lo + (hi - lo) * i / n_cham
                pts.append((cx(t), t))
        return pts + top

    out = []

    def emit(verts):
        g = ShPoly(verts)
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty or g.geom_type != "Polygon" or g.area < min_size * min_size * 0.6:
            return
        ring = [(round(x, 3), round(y, 3)) for x, y in g.exterior.coords]
        rp = g.representative_point()
        out.append((ring, g.area, (round(rp.x, 3), round(rp.y, 3))))

    rows = {}
    for p in real:
        rows.setdefault(round(p["y"], 1), []).append(p)
    tops, bots = [], []
    for yk, r in rows.items():
        y0 = min(p["y"] for p in r); y1 = max(p["y"] + p["h"] for p in r)
        tops.append(y1); bots.append(y0)
        xl = min(p["x"] for p in r); xr = max(p["x"] + p["w"] for p in r)
        # A TAPERED (triangular) gap wastes space under one long diagonal; split it into a FEW
        # stacked single-diagonal pentagons so each hugs the curve closer (client's "divide
        # into two"). Capped at 2-3 pieces (3 only for the sharpest top/bottom corners) to keep
        # the dummy count down; near-uniform gaps stay one piece.
        taper = abs(cx(y0) - cx(y1))
        nb = min(max_bands, 3 if taper >= 12.0 else (2 if taper >= 4.0 else 1))
        while nb > 1 and (y1 - y0) / nb < 4.0:             # no band thinner than ~4mm
            nb -= 1
        for j in range(nb):
            ya = y0 + (y1 - y0) * j / nb
            yb = y0 + (y1 - y0) * (j + 1) / nb
            chain = outer_chain(ya, yb)
            xmax = max(x for x, y in chain)
            if xmax - xr >= min_size:                      # right gap (single-diagonal pentagon)
                emit([(xr, ya)] + chain + [(xr, yb)])
            if xl + xmax >= min_size:                      # left gap (mirror in x)
                emit([(xl, yb)] + [(-x, y) for x, y in reversed(chain)] + [(xl, ya)])
    if tops:
        top, bot = max(tops), min(bots)
        # CAPS: TWO chamfered right-trapezoids per cap (left + right half — the client's two
        # mirror "green" orientations). Each has a single diagonal that follows the circle from
        # the centre apex (0, ±R) down to a short VERTICAL at the outer end (so the outer corner
        # is 90 deg, not acute). All corners >= 90 deg.
        yflat = math.sqrt(max(0.0, R * R - min_size * min_size))   # |y| of the tiny central flat top
        for sgn, base in ((1, top), (-1, bot)):
            h = R - abs(base)                             # cap height (row top -> circle apex)
            if h < min_size:
                continue
            yc = sgn * yflat                              # centre-vertical top (just below the apex)
            if abs(yc) - abs(base) < 0.5:
                continue
            xt = cx(yc)                                   # central flat-top half-width (= min_size)
            yv = base + sgn * min(v_inset, h * 0.6)       # short OUTER vertical foot
            xb = cx(yv)                                   # outer x (foot of the short vertical)
            if xb < min_size:
                continue
            # right half: bottom -> outer short-vertical -> single diagonal -> tiny flat top ->
            # centre vertical (a flat top instead of a sharp apex keeps the centre corner 90 deg)
            emit([(0.0, base), (xb, base), (xb, yv), (xt, yc), (0.0, yc)])
            emit([(0.0, base), (0.0, yc), (-xt, yc), (-xb, yv), (-xb, base)])     # left half (mirror)
    return out


def pool_thin_rows(real, R, min_size):
    """For the MACHINE-CUT fill: a WIDE row centered at y~0 leaves a thin sliver on BOTH sides
    (each < min_size) that can't be filled with a valid dummy. Shift such a row so its slack
    POOLS to one side -> the seed edge sits flush against the circle on the other side (no gap)
    and the pooled side becomes ONE fillable >= min_size gap. Only rows whose BOTH centered
    side-gaps are < min_size are touched (narrow rows keep their symmetric gaps). Returns a
    shifted DEEP COPY (the originals are shared with the other fill sections)."""
    import copy
    real = copy.deepcopy(real)

    def cx(y):
        return math.sqrt(max(0.0, R * R - y * y))

    rows = {}
    for p in real:
        rows.setdefault(round(p["y"], 1), []).append(p)
    for r in rows.values():
        y0 = min(p["y"] for p in r); y1 = max(p["y"] + p["h"] for p in r)
        xl = min(p["x"] for p in r); xr = max(p["x"] + p["w"] for p in r)
        cxn = min(cx(y0), cx(y1))                         # narrowest chord across the row
        lg, rg = xl + cxn, cxn - xr                       # left / right centered gaps
        if lg < min_size and rg < min_size and lg + rg >= min_size:
            for p in r:                                   # make left flush, pool slack to the right
                p["x"] -= lg
    return real


def guillo_plate_job(args):
    """Picklable per-plate worker for the MACHINE-CUT section: real seeds (rows) + TRIANGLE
    dummies from `guillotine_tri_fill` — recursive-guillotine (edge-to-edge of each freed
    piece) triangles reaching the circle. `args` = (real, pi, plate_d, R, min_size, path)."""
    real, pi, plate_d, R, min_size, path = args
    P.PLATE_D = plate_d
    # DUMMY floor (1.5mm) is lower than the REAL-seed floor (min_size, 2mm): the extra 0.5mm
    # lets dummies fill the thin edge slivers beside the widest rows so real-seed CORNERS are
    # backed by dummy material instead of sitting next to a ~2mm empty pocket (chip-risk fix).
    # Real seeds are untouched — only filler shrinks. Also reduces pooling: a 1.5-2mm gap is
    # now fillable on BOTH sides (symmetric support) instead of pooled flush to one side.
    dfloor = min(min_size, 1.5)
    real = pool_thin_rows(real, R, dfloor)                # pool only truly sub-1.5mm wide-row slivers
    placed = list(real)
    # Each row SIDE gap is ONE solid dummy whose outer edge follows the circle with a few
    # straight chords (sub_h spacing) -> no thin sub-strip slivers (old D12 beside a seed
    # corner) AND no flat-trapezoid coverage loss. Caps stay finely stripped (cap_h=4).
    for k, (coords, area, rp) in enumerate(guillotine_tri_fill(real, R, dfloor, sub_h=2.0, cap_h=2.0), 1):
        xs = [c[0] for c in coords]; ys = [c[1] for c in coords]
        bx, by = min(xs), min(ys); bw, bh = max(xs) - bx, max(ys) - by
        placed.append({"stock": f"FILL-{pi:02d}-I{k}", "cts": 0.0, "L": round(bw, 1), "W": round(bh, 1),
                       "H": 0.0, "x": bx, "y": by, "w": bw, "h": bh, "angle": 0, "filler": True,
                       "kind": "irregular", "poly": coords, "area": area, "lx": rp[0], "ly": rp[1]})
    fillH = (round(sum(p["H"] for p in real) / len(real), 3) if real
             else round((P.T_LO + P.T_HI) / 2.0, 3))
    for p in placed:
        if p.get("filler"):
            p["H"] = fillH
    covered = sum(p.get("area", p["w"] * p["h"]) for p in placed)
    fill = 100 * covered / (math.pi * R * R)
    m = 0.0
    for p in placed:
        if p.get("kind") == "irregular":
            for cx, cy in p["poly"]:
                m = max(m, math.hypot(cx, cy))
            continue
        for cx, cy in ((p["x"], p["y"]), (p["x"] + p["w"], p["y"]),
                       (p["x"] + p["w"], p["y"] + p["h"]), (p["x"], p["y"] + p["h"])):
            m = max(m, math.hypot(cx, cy))
    span = 2 * m
    render_cross_circle(placed, real, pi, R, fill, path)
    return (pi, placed, round(fill, 4), round(span, 4), 0.0)


# ---------------------------------------------------------------------------
# ENHANCED VERSION — fill the leftover PERIMETER regions (where real seeds would go,
# but no matching real seed exists) with dummy seed polygons. The free border band is
# cut ALONG THE SEED EDGES and follows the circle with straight chords, so each dummy
# aligns with the seed layout (matching the marked pattern). Every substantial region
# is filled — none skipped. Rendered AMBER, labelled E1..En.
# ---------------------------------------------------------------------------

# Minimum dummy FOOTPRINT (area), equivalent to a 12×12 mm seed. Dummies stay
# IRREGULAR polygons shaped to the available space — this is an area floor, not a
# 12×12 rectangle. Any piece below it is merged into a neighbour until it clears.
ENHANCED_MIN_FOOTPRINT = 12.0 * 12.0   # = 144 mm²


def enhanced_seed_fill(seeds, R, min_area=ENHANCED_MIN_FOOTPRINT):
    """Decompose the free area (usable circle minus real seeds) into IRREGULAR dummy
    polygons aligned to the SEED EDGES (pieces sit above / below / beside the seed
    rows like the marked layout) and following the circle with straight chords. Every
    emitted polygon has a footprint (area) >= `min_area` (12×12-equivalent): smaller
    pieces are repeatedly merged into the neighbour they share the most boundary with,
    so nothing tiny is emitted and no region is dropped. Returns
    [(exterior [(x,y)...], area, (label_x, label_y))]."""
    from shapely.geometry import Point, Polygon as ShPoly, box, MultiPoint
    from shapely.ops import unary_union
    occ = [ShPoly([(p["x"], p["y"]), (p["x"] + p["w"], p["y"]),
                   (p["x"] + p["w"], p["y"] + p["h"]), (p["x"], p["y"] + p["h"])]) for p in seeds]
    su = unary_union(occ) if occ else None
    # Outer outline = convex hull of the seed corners + n_circ points on the usable circle.
    # The hull CUTS each corner with a straight diagonal (the corner triangles in the
    # reference image) while still reaching the circle at those points; subtracting the
    # seeds leaves the perimeter band, which the seed-edge grid below splits into the
    # corner triangles + row caps.
    n_circ = 16
    cpts = [(R * math.cos(2 * math.pi * k / n_circ), R * math.sin(2 * math.pi * k / n_circ))
            for k in range(n_circ)]
    corners = []
    if su is not None:
        for g in (su.geoms if su.geom_type == "MultiPolygon" else [su]):
            corners += list(g.exterior.coords)[:-1]
    outer = MultiPoint(corners + cpts).convex_hull
    free = outer.difference(su) if su is not None else outer
    opened = free.buffer(-0.5, join_style=2).buffer(0.5, join_style=2)  # drop hairline crescents only
    if opened.is_empty:
        return []
    # Cut lines = the seed edges (so pieces align with the seed rows/columns) + circle bbox.
    xs = sorted({-R, R, *[p["x"] for p in seeds], *[p["x"] + p["w"] for p in seeds]})
    ys = sorted({-R, R, *[p["y"] for p in seeds], *[p["y"] + p["h"] for p in seeds]})
    pieces = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            pc = opened.intersection(box(xs[i], ys[j], xs[i + 1], ys[j + 1]))
            if pc.is_empty:
                continue
            for g in (pc.geoms if pc.geom_type in ("MultiPolygon", "GeometryCollection") else [pc]):
                if getattr(g, "geom_type", "") == "Polygon" and not g.is_empty and g.area > 1.0:
                    pieces.append(g)
    # Grow sub-144 (12×12-footprint) pieces by merging each into the neighbour it shares
    # the most boundary with — but NEVER drop a region: a piece that cannot merge cleanly
    # is kept as-is, so the WHOLE perimeter stays filled (matching the marked layout).
    done_ids = set()
    guard = 0
    while guard < 2000:
        guard += 1
        small = [i for i, p in enumerate(pieces) if p.area < min_area and id(p) not in done_ids]
        if not small:
            break
        i = min(small, key=lambda k: pieces[k].area)          # smallest first
        tb = pieces[i].buffer(0.15)
        best_j, best = -1, 0.0
        for j, gp in enumerate(pieces):
            if j == i:
                continue
            a = tb.intersection(gp.buffer(0.15)).area
            if a > best:
                best, best_j = a, j
        if best_j < 0:                                        # nothing adjacent → keep as-is
            done_ids.add(id(pieces[i]))
            continue
        merged = unary_union([pieces[i], pieces[best_j]])
        if merged.geom_type == "Polygon":
            pieces.pop(i)
            if best_j > i:
                best_j -= 1
            pieces[best_j] = merged                           # neighbour absorbs it (grows toward 12×12)
        else:
            done_ids.add(id(pieces[i]))                       # only touches at a point → keep as-is
    out = []
    for h in pieces:
        if h.area < 15.0:                                     # drop only micro-slivers
            continue
        h = h.simplify(0.5)                                   # straight edges; merge near-collinear
        if not h.is_valid:
            h = h.buffer(0)
        if h.is_empty or h.geom_type != "Polygon":
            continue
        rp = h.representative_point()
        out.append(([(round(x, 3), round(y, 3)) for x, y in h.exterior.coords],
                    h.area, (round(rp.x, 3), round(rp.y, 3))))
    return out


ENHANCED_MIN_DUMMY_AREA = 4.0    # mm² — smallest manufacturable dummy shape is 2×2 mm
                                 # (right trapezoid 2×2×2 mm); anything smaller is discarded


def _poly_diameter(coords):
    """Diameter of a shape = the largest distance between any two of its vertices."""
    d = 0.0
    n = len(coords)
    for i in range(n):
        xi, yi = coords[i]
        for j in range(i + 1, n):
            v = math.hypot(xi - coords[j][0], yi - coords[j][1])
            if v > d:
                d = v
    return d


def _surrounded(s, real):
    """True if seat `s` has at least one packed seat on EACH of its four sides (a fully
    surrounded interior seat). Left/right neighbours must share its row band; up/down
    must share its column band. These are exactly the seats the client ticks as real."""
    scx, scy = s["x"] + s["w"] / 2, s["y"] + s["h"] / 2

    def row_band(o):    # shares a horizontal band (same row)
        return (min(o["y"] + o["h"], s["y"] + s["h"]) - max(o["y"], s["y"])) > 0.3 * min(o["h"], s["h"])

    def col_band(o):    # shares a vertical band (same column)
        return (min(o["x"] + o["w"], s["x"] + s["w"]) - max(o["x"], s["x"])) > 0.3 * min(o["w"], s["w"])

    left = right = up = down = False
    for o in real:
        if o is s:
            continue
        ocx, ocy = o["x"] + o["w"] / 2, o["y"] + o["h"] / 2
        if row_band(o):
            if ocx < scx - 0.3 * s["w"]:
                left = True
            elif ocx > scx + 0.3 * s["w"]:
                right = True
        if col_band(o):
            if ocy > scy + 0.3 * s["h"]:
                up = True
            elif ocy < scy - 0.3 * s["h"]:
                down = True
    return left and right and up and down


def enhanced_grid_fill(real, R, min_dummy_area=ENHANCED_MIN_DUMMY_AREA):
    """ENHANCED VERSION — packing-based (matches the client's marked reference image).
    Base = the REAL packed arrangement (rows of real seeds, e.g. 2-4-5-4-2). Split it:

      REAL  — a seat that is SURROUNDED on all four sides by other seats (the fully
              interior seats — exactly the ones the client ticks). Kept as its own
              rectangle with its real stock / size.
      DUMMY — everything else: the whole plate area MINUS the real rectangles. That
              region (every edge seat + the leftover band out to the circle) is cut
              along the packed seed grid-lines and clipped to the plate circle, yielding
              WHOLE trapezoid / pentagon / triangle pieces (the shapes the client
              listed). Sub-min slivers are folded into their neighbour; thin gaps that
              only touch real seeds are dropped (ignored) — no thin lines. Each dummy is
              labelled with its diameter.

    Returns (real_cells, dummy_cells):
      real_cells  = [seed dict ...]                             surrounded interior seats
      dummy_cells = [([(x,y)...], area, diameter, (lx,ly)) ...] boundary shapes
    """
    from shapely.geometry import Point, box, MultiPoint
    from shapely.ops import unary_union, voronoi_diagram
    if not real:
        return [], []
    disc = Point(0.0, 0.0).buffer(R, resolution=96)
    real_cells = [s for s in real if _surrounded(s, real)]
    surrounded = {id(s) for s in real_cells}
    perim = [s for s in real if id(s) not in surrounded]
    if not perim:
        return real_cells, []

    def _rect(s):
        return box(s["x"], s["y"], s["x"] + s["w"], s["y"] + s["h"])

    def _emit(g, out):
        g = g.simplify(0.4)
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty or g.geom_type != "Polygon" or g.area < min_dummy_area:
            return
        coords = [(round(x, 3), round(y, 3)) for x, y in g.exterior.coords]
        rp = g.representative_point()
        out.append((coords, g.area, _poly_diameter(coords), (round(rp.x, 3), round(rp.y, 3))))

    # The RING = plate circle minus the real interior block. Partition it with a Voronoi
    # tessellation of the PERIMETER seat centres: each perimeter seat owns one convex
    # territory that spans from the real block out to the circle. So every dummy is one
    # clean piece for one seat position, reaching the rim (like the client's drawn
    # trapezoids / pentagons / corner triangles) — the whole ring is covered, nothing thin.
    real_union = unary_union([_rect(s) for s in real_cells]) if real_cells else None
    ring = disc.difference(real_union) if real_union is not None else disc
    pts = [(s["x"] + s["w"] / 2.0, s["y"] + s["h"] / 2.0) for s in perim]
    try:
        regions = list(voronoi_diagram(MultiPoint([Point(p) for p in pts]), envelope=disc).geoms)
    except Exception:
        return real_cells, []
    dummy_cells = []
    for idx in range(len(perim)):
        c = Point(pts[idx])
        cell = next((g for g in regions if g.covers(c)), None)
        if cell is None:
            continue
        piece = cell.intersection(ring)
        if piece.is_empty:
            continue
        for g in (piece.geoms if piece.geom_type in ("MultiPolygon", "GeometryCollection") else [piece]):
            if getattr(g, "geom_type", "") == "Polygon":
                _emit(g, dummy_cells)
    return real_cells, dummy_cells


def _clip_straight(rect_poly, disc, R, eps=0.4):
    """Clip a seed rectangle to the plate disc, then replace the circular-arc portion of
    the boundary with a SINGLE straight chord between the two points where the seed crosses
    the circle (the client's 'cut with a straight line' rule). Returns a Polygon or None."""
    from shapely.geometry import Polygon as ShPoly
    g = rect_poly.intersection(disc)
    if g.is_empty:
        return None
    if g.geom_type != "Polygon":
        g = max((p for p in g.geoms if p.geom_type == "Polygon"), key=lambda p: p.area, default=None)
        if g is None:
            return None
    coords = list(g.exterior.coords)[:-1]
    n = len(coords)
    if n < 3:
        return None

    def on_c(p):
        return abs(math.hypot(p[0], p[1]) - R) < eps

    out = []
    for i, p in enumerate(coords):
        if not on_c(p):
            out.append(p)                                    # a seed corner (inside) — keep
        else:
            prv, nxt = coords[(i - 1) % n], coords[(i + 1) % n]
            if not on_c(prv) or not on_c(nxt):
                out.append(p)                                # arc endpoint — keep (chord ends here)
            # else: interior arc vertex → drop, so the arc collapses to one straight chord
    if len(out) < 3:
        return None
    poly = ShPoly(out)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if (not poly.is_empty and poly.geom_type == "Polygon") else None


# Manufacturing rule: a straight cut must never leave a corner sharper than 90°, and no
# cut facet shorter than this (mm). Acute corners = fragile sharp points on the machine.
MIN_CUT_MM = 2.0


def _chamfer_ge90(poly, min_edge=MIN_CUT_MM, min_angle_deg=90.0, max_iter=14):
    """Return a polygon whose every interior angle is >= min_angle_deg (default 90°) by
    CHAMFERING each acute convex corner with a straight diagonal facet at least `min_edge`
    long (the client's ≥90° / min-2mm rule). Right angles and reflex (notch) corners are
    left untouched, so full rectangles pass through unchanged."""
    from shapely.geometry import Polygon as ShPoly
    from shapely.geometry.polygon import orient
    if poly is None or poly.is_empty or poly.geom_type != "Polygon":
        return poly
    thr = math.radians(min_angle_deg) - math.radians(1.0)   # 1° tolerance
    try:
        poly = orient(poly, 1.0)                            # force CCW so turns are signed
    except Exception:
        return poly
    for _ in range(max_iter):
        ring = list(poly.exterior.coords)[:-1]
        n = len(ring)
        if n < 3:
            return poly
        worst = None
        for i in range(n):
            a = ring[(i - 1) % n]; b = ring[i]; c = ring[(i + 1) % n]
            v1x, v1y = a[0] - b[0], a[1] - b[1]
            v2x, v2y = c[0] - b[0], c[1] - b[1]
            l1 = math.hypot(v1x, v1y); l2 = math.hypot(v2x, v2y)
            if l1 < 1e-9 or l2 < 1e-9:
                continue
            dot = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (l1 * l2)))
            edge_ang = math.acos(dot)                       # undirected angle between the two edges
            turn = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            interior = edge_ang if turn > 0 else (2 * math.pi - edge_ang)   # reflex → >180°
            if interior < thr and (worst is None or interior < worst[0]):
                worst = (interior, i, a, b, c, l1, l2)
        if worst is None:
            break                                           # all corners already >= 90°
        interior, i, a, b, c, l1, l2 = worst
        s = math.sin(interior / 2.0)
        d = max(min_edge, (min_edge / (2 * s)) if s > 1e-6 else min_edge)
        d = min(d, 0.45 * l1, 0.45 * l2)                    # don't overrun either edge
        ua = ((a[0] - b[0]) / l1, (a[1] - b[1]) / l1)
        uc = ((c[0] - b[0]) / l2, (c[1] - b[1]) / l2)
        p = (b[0] + ua[0] * d, b[1] + ua[1] * d)
        q = (b[0] + uc[0] * d, b[1] + uc[1] * d)
        newring = ring[:i] + [p, q] + ring[i + 1:]          # replace the sharp vertex with a facet
        np_ = ShPoly(newring)
        if not np_.is_valid:
            np_ = np_.buffer(0)
        if np_.is_empty or np_.geom_type != "Polygon":
            break
        poly = np_
    return poly


def _square_ge90(poly, min_edge=MIN_CUT_MM, min_angle_deg=90.0, max_iter=16, protect=None):
    """Same goal as `_chamfer_ge90` (no interior angle < 90°, no cut facet < min_edge) but
    the relief cut is a STRAIGHT AXIS-ALIGNED line (perpendicular to the seed's own straight
    edge), not a diagonal bevel — the client's 'straight, not diagonal' cut. At an acute
    corner we cut perpendicular to the more axis-aligned of the two edges; that makes the new
    corner on that edge exactly 90° and the other 90°+α, so both stay >= 90°.

    `protect` = set of (round(x,1), round(y,1)) corners that are SHARED with an adjacent seat
    (internal cut junctions, not free tips) — these are left untouched so relieving one seat's
    corner never opens a notch where it meets its neighbour."""
    from shapely.geometry import Polygon as ShPoly
    from shapely.geometry.polygon import orient
    if poly is None or poly.is_empty or poly.geom_type != "Polygon":
        return poly
    # STRICT: relieve every corner below 90° (tiny 0.02° slack only so a true right angle on a
    # full rectangle isn't touched by floating-point noise). No corner is left 1-2° under 90°.
    thr = math.radians(min_angle_deg) - math.radians(0.02)
    try:
        poly = orient(poly, 1.0)
    except Exception:
        return poly
    for _ in range(max_iter):
        ring = list(poly.exterior.coords)[:-1]
        n = len(ring)
        if n < 3:
            return poly
        worst = None
        for i in range(n):
            a = ring[(i - 1) % n]; b = ring[i]; c = ring[(i + 1) % n]
            if protect and (round(b[0], 1), round(b[1], 1)) in protect:
                continue                                    # shared junction corner → leave it
            v1x, v1y = a[0] - b[0], a[1] - b[1]
            v2x, v2y = c[0] - b[0], c[1] - b[1]
            l1 = math.hypot(v1x, v1y); l2 = math.hypot(v2x, v2y)
            if l1 < 1e-9 or l2 < 1e-9:
                continue
            dot = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (l1 * l2)))
            edge_ang = math.acos(dot)
            turn = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            interior = edge_ang if turn > 0 else (2 * math.pi - edge_ang)
            if interior < thr and (worst is None or interior < worst[0]):
                worst = (interior, i, a, b, c, l1, l2)
        if worst is None:
            break
        interior, i, a, b, c, l1, l2 = worst
        # base edge = the one nearest an axis (so the perpendicular cut is horizontal/vertical)
        sa1 = max(abs((a[0] - b[0]) / l1), abs((a[1] - b[1]) / l1))
        sa2 = max(abs((c[0] - b[0]) / l2), abs((c[1] - b[1]) / l2))
        if sa2 >= sa1:
            base, lb, slant, ls, base_is_c = c, l2, a, l1, True
        else:
            base, lb, slant, ls, base_is_c = a, l1, c, l2, False
        ca = max(math.cos(interior), 1e-3); sn = max(math.sin(interior), 0.15)
        p = max(min_edge, min_edge / sn)                    # facet length = p·sinα >= min_edge
        p = min(p, 0.45 * ls, 0.45 * lb / ca)               # don't overrun either edge
        q = p * ca
        us = ((slant[0] - b[0]) / ls, (slant[1] - b[1]) / ls)
        ub = ((base[0] - b[0]) / lb, (base[1] - b[1]) / lb)
        pt_p = (b[0] + us[0] * p, b[1] + us[1] * p)         # on the slant (chord) edge
        pt_q = (b[0] + ub[0] * q, b[1] + ub[1] * q)         # foot on the axis-aligned edge (90°)
        seq = [pt_p, pt_q] if base_is_c else [pt_q, pt_p]   # keep CCW order a→…→c
        newring = ring[:i] + seq + ring[i + 1:]
        np_ = ShPoly(newring)
        if not np_.is_valid:
            np_ = np_.buffer(0)
        if np_.is_empty or np_.geom_type != "Polygon":
            break
        poly = np_
    return poly


def _min_interior_angle(ring):
    """Smallest interior angle (degrees) of a polygon given as a list of (x,y) vertices."""
    from shapely.geometry import Polygon as ShPoly
    from shapely.geometry.polygon import orient
    try:
        r = list(orient(ShPoly(ring), 1.0).exterior.coords)[:-1]
    except Exception:
        return 0.0
    n = len(r); mn = 999.0
    for i in range(n):
        a = r[(i - 1) % n]; b = r[i]; c = r[(i + 1) % n]
        v1x, v1y = a[0] - b[0], a[1] - b[1]
        v2x, v2y = c[0] - b[0], c[1] - b[1]
        l1 = math.hypot(v1x, v1y); l2 = math.hypot(v2x, v2y)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        dot = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (l1 * l2)))
        ea = math.degrees(math.acos(dot))
        turn = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        mn = min(mn, ea if turn > 0 else 360.0 - ea)
    return mn


def _drop_step_vertex(poly, R, max_dev=2.5):
    """If a boundary seat has an extra 'step' vertex on its outer edge (a hexagon+), remove the
    single lowest-deviation vertex whose removal keeps EVERY interior angle >= 90° and stays
    inside the circle — merging two chord segments into ONE straight cut (e.g. hexagon→pentagon).
    Only ever removes one vertex, and only when it never makes an angle sharper than 90°."""
    from shapely.geometry import Polygon as ShPoly
    if poly is None or poly.is_empty or poly.geom_type != "Polygon":
        return poly
    ring = list(poly.exterior.coords)[:-1]
    n = len(ring)
    if n < 6:
        return poly
    best = None
    for i in range(n):
        v = ring[i]; a = ring[(i - 1) % n]; c = ring[(i + 1) % n]
        dx = c[0] - a[0]; dy = c[1] - a[1]; L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        d = abs((v[0] - a[0]) * dy - (v[1] - a[1]) * dx) / L      # how far v sits off the a–c line
        if d > max_dev:
            continue
        nr = ring[:i] + ring[i + 1:]
        g = ShPoly(nr)
        if not g.is_valid or g.geom_type != "Polygon" or g.is_empty:
            continue
        if _min_interior_angle(nr) >= 89.0 and max(math.hypot(x, y) for x, y in nr) <= R + 0.05:
            if best is None or d < best[0]:
                best = (d, g)
    return best[1] if best else poly


def _touch_ring_corner(poly, R, tol=1.9):
    """Push each near-boundary convex RIM corner outward until its vertex lands EXACTLY on the
    plate circle — closing the corner-gap without re-shaping the edges (the client's 'move only
    the corner where the two edge lines meet to the circle' rule). The two edges stay straight;
    the vertex moves along a vertical/horizontal adjacent edge when that keeps it as short as a
    radial move (so a shared seat edge stays aligned), else radially. A corner is moved only if
    it genuinely faces the rim (not an inner/shared structural corner) AND the move keeps every
    interior angle >= 90° — so hard 90° shoulder corners are left untouched. Returns Polygon."""
    from shapely.geometry import Polygon as ShPoly
    from shapely.geometry.polygon import orient
    if poly is None or poly.is_empty or poly.geom_type != "Polygon":
        return poly
    try:
        o = orient(poly, 1.0)                                # CCW so a convex apex has a right turn
    except Exception:
        return poly
    ring = list(o.exterior.coords)[:-1]
    n = len(ring)
    if n < 3:
        return poly
    out = list(ring)
    moved = 0
    AX = 0.06                                                # |component| below this = axis-aligned edge
    face = math.cos(math.radians(65))
    for i in range(n):
        vx, vy = ring[i]
        r = math.hypot(vx, vy)
        if not (0.05 < R - r < tol):
            continue
        ax, ay = ring[(i - 1) % n]
        bx, by = ring[(i + 1) % n]
        e1 = (ax - vx, ay - vy); e2 = (bx - vx, by - vy)
        l1 = math.hypot(*e1); l2 = math.hypot(*e2)
        if l1 < 1e-6 or l2 < 1e-6:
            continue
        u1 = (e1[0] / l1, e1[1] / l1); u2 = (e2[0] / l2, e2[1] / l2)
        if (u1[0] * u2[1] - u1[1] * u2[0]) >= -1e-3:         # skip reflex / flat — only convex apexes
            continue
        exb = (-(u1[0] + u2[0]), -(u1[1] + u2[1]))           # exterior (outward) bisector
        le = math.hypot(*exb)
        if le < 1e-6:
            continue
        if (exb[0] / le) * (vx / r) + (exb[1] / le) * (vy / r) < face:   # corner must face the rim
            continue
        cands = [((vx * R / r, vy * R / r), R - r)]          # radial snap (default)
        if (abs(e1[0]) < AX or abs(e2[0]) < AX) and R * R - vx * vx > 0:  # keep a vertical edge → move y
            ny = math.copysign(math.sqrt(R * R - vx * vx), vy); cands.append(((vx, ny), abs(ny - vy)))
        if (abs(e1[1]) < AX or abs(e2[1]) < AX) and R * R - vy * vy > 0:  # keep a horizontal edge → move x
            nx = math.copysign(math.sqrt(R * R - vy * vy), vx); cands.append(((nx, vy), abs(nx - vx)))
        axis = [c for c in cands[1:] if c[1] <= (R - r) + 0.3]           # prefer an axis move if ~as short
        tgt = (min(axis, key=lambda c: c[1]) if axis else min(cands, key=lambda c: c[1]))[0]
        if math.hypot(tgt[0] - vx, tgt[1] - vy) > tol + 0.4:
            continue
        out[i] = tgt
        moved += 1
    if not moved:
        return poly
    g = ShPoly(out)
    if not g.is_valid:
        g = g.buffer(0)
    if g.is_empty or g.geom_type != "Polygon" or not g.exterior.is_simple:
        return poly
    if _min_interior_angle(out) < 89.4:                      # never create a sub-90° cut
        return poly
    if max(math.hypot(x, y) for x, y in out) > R + 1e-4:     # never cross the plate boundary
        return poly
    return g


# Number of sides for the straight-edged cutting boundary inscribed in the plate circle.
# 8 → flat top/bottom/left/right + ONE clean diagonal per corner region (the client's
# "one clean diagonal per edge region" rule). All interior angles are 135° (≥90°).
BOUNDARY_SIDES = 8


def _boundary_polygon(R, n=BOUNDARY_SIDES):
    """A regular n-gon inscribed in the plate circle (radius R), rotated so it has a FLAT
    top, bottom, left and right edge and one diagonal edge per corner. Seats are cut to
    THIS instead of the raw circle, so every seat along a region shares one straight cut
    line — no per-seat sawtooth — while no cut angle drops below 90°."""
    from shapely.geometry import Polygon as ShPoly
    base = math.pi / n                                   # rotate so edges (not vertices) sit at top/sides
    return ShPoly([(R * math.cos(base + 2 * math.pi * k / n),
                    R * math.sin(base + 2 * math.pi * k / n)) for k in range(n)])


def _snap_clean(poly, grid=MIN_CUT_MM):
    """Snap a rectilinear seat polygon's vertices to the `grid` (2mm) and drop the resulting
    zero/near-zero-length edges, so no cut feature is shorter than the grid. Keeps the shape
    axis-aligned (all cuts stay horizontal/vertical)."""
    from shapely.geometry import Polygon as ShPoly
    if poly is None or poly.is_empty or poly.geom_type != "Polygon":
        return poly
    snapped = [(round(x / grid) * grid, round(y / grid) * grid) for x, y in poly.exterior.coords]
    out = []
    for pt in snapped:
        if not out or abs(pt[0] - out[-1][0]) > 1e-9 or abs(pt[1] - out[-1][1]) > 1e-9:
            out.append(pt)
    if len(out) >= 2 and out[0] == out[-1]:
        out = out[:-1]
    if len(out) < 3:
        return None
    p = ShPoly(out)
    if not p.is_valid:
        p = p.buffer(0)
    return p if (not p.is_empty and p.geom_type == "Polygon") else None


def _reach_ring(poly, R, tol=1.6):
    """Extend a trimmed seat out to the plate boundary where its ≥90° relief left it a hair
    short — but do it by sliding each near-boundary vertex ALONG its adjacent axis-aligned
    relief facet (keeping that cut PERFECTLY vertical/horizontal), never by tilting the edge.
    A vertex on a vertical facet moves in y only (x fixed); on a horizontal facet, in x only."""
    from shapely.geometry import Polygon as ShPoly
    if poly is None or poly.is_empty or poly.geom_type != "Polygon":
        return poly
    ring = list(poly.exterior.coords)[:-1]
    n = len(ring)
    if n < 3:
        return poly
    out = list(ring)
    for i in range(n):
        v = ring[i]
        r = math.hypot(v[0], v[1])
        if not (0.05 < R - r < tol):                      # only vertices a hair inside the boundary
            continue
        prev = ring[(i - 1) % n]; nxt = ring[(i + 1) % n]
        # classify BOTH adjacent edges: axis-aligned ('V'/'H') or a chord (None)
        cls = []
        for o in (prev, nxt):
            dx = o[0] - v[0]; dy = o[1] - v[1]; el = math.hypot(dx, dy)
            axis = None
            if el >= 1e-6:
                axis = 'V' if abs(dx) < 0.06 else ('H' if abs(dy) < 0.06 else None)
            cls.append((axis, el))
        aa = [c for c in cls if c[0]]
        # Only nudge a vertex that sits between ONE short axis-aligned relief facet and a chord.
        # (Two axis edges = a clean right-angle corner → moving it would tilt the other edge.)
        if len(aa) != 1 or aa[0][1] > 6.0:
            continue
        axis = aa[0][0]
        if axis == 'V':                                   # keep x, slide in y to the ring
            disc_ = R * R - v[0] * v[0]
            if disc_ > 0:
                out[i] = (v[0], math.copysign(math.sqrt(disc_), v[1] if v[1] else 1.0))
        else:                                             # keep y, slide in x to the ring
            disc_ = R * R - v[1] * v[1]
            if disc_ > 0:
                out[i] = (math.copysign(math.sqrt(disc_), v[0] if v[0] else 1.0), v[1])
    p = ShPoly(out)
    if not p.is_valid:
        p = p.buffer(0)
    return p if (not p.is_empty and p.geom_type == "Polygon") else poly


def _stepped_disc(R, step=MIN_CUT_MM):
    """A RECTILINEAR (axis-aligned staircase) inscribed approximation of the plate circle —
    never exceeds the circle. Seats cut to THIS get ONLY horizontal/vertical cut lines (small
    right-angle steps that hug the curve, never a diagonal), and every step is a multiple of
    `step` (≥ the 2mm minimum). Every corner is 90° or 270° — no sub-90° points."""
    from shapely.geometry import box as shbox
    from shapely.ops import unary_union
    cols = []
    x = -R
    while x < R - 1e-9:
        x2 = min(x + step, R)
        xm = max(abs(x), abs(x2))                        # worst-case x across the column
        if xm < R:
            h = math.floor(math.sqrt(R * R - xm * xm) / step) * step   # snap inward to the grid
            if h >= step:
                cols.append(shbox(x, -h, x2, h))
        x = x2
    return unary_union(cols)


def _clip_to(rect, bnd):
    """Intersect a seat rectangle with the (straight-edged) cutting boundary; return the
    largest resulting Polygon (or None). Straight boundary → straight cuts, no arc."""
    g = rect.intersection(bnd)
    if g.is_empty:
        return None
    if g.geom_type != "Polygon":
        g = max((p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"),
                key=lambda p: p.area, default=None)
    return g


def _draw_plate_numbers(ax, items):
    """Label each seat on the plate with just a NUMBER (or D-number) — bold with a dark
    halo so it stays readable in any seat size / fill colour. items = list of
    (label, lx, ly, area, color)."""
    halo = [pe.withStroke(linewidth=2.6, foreground="#0d0d0dee")]
    for label, lx, ly, area, color in items:
        fs = min(14.0, max(8.0, math.sqrt(max(area, 1.0)) * 0.7))
        ax.text(lx, ly, label, ha="center", va="center", fontsize=fs,
                color=color, fontweight="bold", zorder=3, path_effects=halo)


def _draw_legend_list(axl, title, subtitle, entries):
    """Draw the seed list beside the plate. entries = list of
    (swatch_color, swatch_edge, number_text, description_text, text_color)."""
    axl.axis("off"); axl.set_xlim(0, 1); axl.set_ylim(0, 1)
    axl.text(0.0, 0.995, title, fontsize=12, fontweight="bold", va="top")
    top = 0.955
    if subtitle:
        axl.text(0.0, 0.965, subtitle, fontsize=8.5, va="top", color="#7a3d00")
        top = 0.925
    n = max(len(entries), 1)
    bot = 0.005
    rh = (top - bot) / n
    lfs = min(8.6, max(5.5, 190.0 / n))
    for i, (color, edge, num, text, tcolor) in enumerate(entries):
        y = top - (i + 0.5) * rh
        axl.add_patch(Rect((0.005, y - rh * 0.34), 0.045, rh * 0.68, facecolor=color,
                      edgecolor=edge, lw=1.0, transform=axl.transAxes, clip_on=False))
        axl.text(0.065, y, num, fontsize=lfs, va="center", fontweight="bold")
        axl.text(0.135, y, text, fontsize=lfs, va="center", color=tcolor)


def render_enhanced_circle(placed, real, pi, R, fill, path):
    """Render a MAX COVERAGE plate: every seed placed WHOLE at its measured shape.

    The engine never cuts a seed, so nothing here is trimmed. The drawing shows
    the two settings that decide the layout, because a plate is hard to judge
    without them: the MARGIN (the ring kept clear around the plate, drawn shaded
    between the plate edge and the dashed usable circle) and the DISTANCE BETWEEN
    SEEDS (the gap held between neighbours).
    """
    PLATE = P.PLATE_D
    margin = max(0.0, PLATE / 2.0 - R)
    seed_gap = max(0.0, float(getattr(P, "CLEARANCE", 0.0) or 0.0))
    nr = len(placed)
    n_clip = sum(1 for p in placed if p.get("clipped"))
    cmap = plt.cm.viridis
    facecolors = [cmap(i / max(1, nr - 1)) for i in range(nr)]

    # Two panels: the plate (each seed labelled with a NUMBER only, so it stays readable in
    # any seat) and, beside it, a full seed LIST — a colour swatch matching the seat plus the
    # stock, size, thickness, and (for trimmed seeds) how much was cut off.
    fig = plt.figure(figsize=(14.5, 9.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[9.6, 5.0], wspace=0.02)
    ax = fig.add_subplot(gs[0, 0])
    axl = fig.add_subplot(gs[0, 1]); axl.axis("off")

    ax.add_patch(Circle((0, 0), PLATE / 2, fc="#e9e9ec", ec="#888", lw=1.5, zorder=0))
    # Shade the MARGIN ring itself, so the clear band reads as a deliberate
    # setting rather than space the packer failed to use.
    if margin > 0.01:
        ax.add_patch(Circle((0, 0), PLATE / 2, fc="#f6dcd7", ec="none", zorder=0.4))
        ax.add_patch(Circle((0, 0), R, fc="#e9e9ec", ec="none", zorder=0.5))
    ax.add_patch(Circle((0, 0), R, fc="none", ec="#c0392b", lw=1.2, ls="--", zorder=1))
    if margin > 0.01:
        # Call the ring out once, with a leader from the plate edge to the
        # usable circle at the 45° diagonal, where seeds rarely reach.
        d = 0.7071
        ax.annotate(
            f"margin {margin:g} mm",
            xy=(-(R + margin * 0.5) * d, (R + margin * 0.5) * d),
            xytext=(-(PLATE / 2 + 1) * d - 12, (PLATE / 2 + 1) * d + 6),
            fontsize=9, color="#a03a2c", ha="center", va="bottom", zorder=6,
            arrowprops=dict(arrowstyle="-", color="#a03a2c", lw=0.9,
                            shrinkA=0, shrinkB=1))
    if placed:                                          # all real seeds as polygons (full or clipped)
        # ZERO-GAP look: paint each whole seed's edge in its OWN fill colour so the thin
        # anti-aliasing seam matplotlib leaves between abutting patches is covered — no
        # white/dark line between seeds. TRIMMED seeds keep an ORANGE outline.
        edgecolors = ["#e67e22" if p.get("clipped") else facecolors[i] for i, p in enumerate(placed)]
        linewidths = [1.4 if p.get("clipped") else 1.0 for p in placed]
        ax.add_collection(PatchCollection([MplPoly(p["poly"], closed=True) for p in placed],
                          facecolor=facecolors, edgecolors=edgecolors, linewidths=linewidths, zorder=2))
    # NUMBER each seat (1..N) — a number fits any seat size.
    _draw_plate_numbers(ax, [(str(i + 1), p.get("lx"), p.get("ly"),
                              p.get("area", p["w"] * p["h"]), "white") for i, p in enumerate(placed)])
    lim = PLATE / 2 + 3
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_aspect("equal"); ax.axis("off")
    circle_area = math.pi * R * R
    covered = fill / 100.0 * circle_area
    # State the settings that shaped this plate. "edge cuts ≥90°" used to sit here
    # and is gone: the engine no longer cuts anything, so it described behaviour
    # that no longer exists.
    ax.set_title(
        f"Max Coverage · Plate {pi:02d} · {covered:.0f} of {circle_area:.0f} mm² covered "
        f"({fill:.1f}%)\n"
        f"plate Ø{PLATE:g} · margin {margin:g} mm → usable Ø{2 * R:g} · "
        f"distance between seeds {seed_gap:g} mm",
        fontsize=10.5)

    # ---- seed list on the right ----
    entries = []
    trimmed = []
    for i, p in enumerate(placed):
        cut, tcolor = "", "#111"
        # How much of the STONE was lost — not how much the plate edge took off
        # its seat. A stone smaller than its clipped seat still fits whole, so it
        # is not trimmed at all. See engine_runner.seed_cut for the reasoning.
        rem, pct = _seed_cut(p)
        if rem > 0.005:
            trimmed.append(i)
            cut, tcolor = f"   ✂ cut {rem:.0f} mm² ({pct:.0f}%)", "#c0392b"
        # Size = the seed's REAL stone measurement from the import (rawL × rawW), so
        # each stock ID reports its true size rather than the cut seat it tiles into.
        # Falls back to the seat box for any seed without stored raw dims (e.g. fillers).
        dw = p.get("rawL") if p.get("rawL") is not None else p["w"]
        dh = p.get("rawW") if p.get("rawW") is not None else p["h"]
        # Exact stored measurement (decimal(18,2)) — no round-off, trailing zeros trimmed.
        sdw = f"{float(dw):.2f}".rstrip("0").rstrip(".")
        sdh = f"{float(dh):.2f}".rstrip("0").rstrip(".")
        entries.append((facecolors[i], "#e67e22" if i in trimmed else "#555", f"{i + 1}.",
                        f"{p['stock']}   {sdw}×{sdh}   H {p['H']:.2f}{cut}", tcolor))
    # The old subtitle counted trimmed seeds and is now permanently zero, so it
    # said nothing. Report the settings the reader actually needs instead.
    _draw_legend_list(
        axl, f"Seeds on this plate ({nr})",
        f"all placed whole (nothing cut) · {seed_gap:g} mm between seeds"
        if seed_gap > 0 else "all placed whole (nothing cut) · seeds touching",
        entries)

    fig.savefig(path, dpi=125, bbox_inches="tight")
    plt.close(fig)


def _seed_cut(p):
    """(cut_mm2, cut_pct) for one placed stone — how much of the STONE was lost.

    Thin wrapper so the plate image and the seed-list table share ONE definition;
    they previously each computed it, and both measured the seat instead of the
    stone. Falls back to "nothing cut" if the Django package is not importable,
    so this module still runs standalone.
    """
    try:
        from modules.production.engine_runner import seed_cut
    except ImportError:
        return 0.0, 0.0
    return seed_cut(p)


def _shape_of(coords):
    """[(x, y), ...] -> shapely Polygon, so a fitted stone outline can be used
    wherever a seat polygon was used before."""
    from shapely.geometry import Polygon as ShPoly

    p = ShPoly(coords)
    return p if p.is_valid else p.buffer(0)


def _fit_seat(pts, seat):
    """Place an irregular stone's outline WHOLE inside a seat, or None if it will
    not fit in any tried orientation.

    Deliberately no software trimming. Cutting a seed is a physical step on the
    shop floor, so an engine that silently shrank a stone to make it "fit" would
    be reporting coverage it has not earned. Accuracy first: a stone that does
    not fit is not placed, and the coverage figure is lower and true.

    Thin wrapper so the geometry lives in modules.production.shapes (pure, unit
    tested) while this engine module stays importable on its own: if the Django
    package isn't on the path, irregular stones quietly fall back rather than
    raising.
    """
    try:
        from modules.production.shapes import fit_polygon_in_seat
    except ImportError:
        return None
    return fit_polygon_in_seat(pts, seat)


def _cut_direction(g):
    """Unit vector from a seed's centre toward the corner ground off it, or None
    for a plain square/rectangle.

    The missing corner is whatever the outline lacks compared with its own
    bounding box, so this works for any pre-cut shape without being told which
    corner was taken.
    """
    from shapely.geometry import box

    bx0, by0, bx1, by1 = g.bounds
    missing = box(bx0, by0, bx1, by1).difference(g)
    if missing.is_empty or missing.area < 0.01:
        return None
    c, m = g.centroid, missing.centroid
    dx, dy = m.x - c.x, m.y - c.y
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-9 else None


def _wasted_area(g, disc):
    """Plate area lost to this seed's ground-off corner, in mm2.

    Only the part of the missing corner that lies INSIDE the plate counts. A cut
    seed set against the rim loses almost nothing, because the corner it lacks is
    beyond the boundary in any case; the same seed in the middle of the plate
    loses the whole triangle. Zero for a plain square or rectangle.
    """
    from shapely.geometry import box

    bx0, by0, bx1, by1 = g.bounds
    missing = box(bx0, by0, bx1, by1).difference(g)
    if missing.is_empty or missing.area < 0.01:
        return 0.0
    return missing.intersection(disc).area


def _outward_score(g, base_cut, deg):
    """How well a placed seed's cut faces AWAY from the plate centre: +1 straight
    out, -1 straight in, 0 for a seed with no cut.

    A seed is ground down because the plate is round — the cut exists to sit
    against the curve. Turned inward it does the opposite of its purpose and
    opens a wedge against its neighbour; turned outward it follows the rim and
    costs nothing. Scoring every orientation and keeping the outward-most is what
    puts a right-cut seed on the right of the plate.
    """
    if not base_cut:
        return 0.0
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    dx = base_cut[0] * ca - base_cut[1] * sa
    dy = base_cut[0] * sa + base_cut[1] * ca
    c = g.centroid
    r = math.hypot(c.x, c.y)
    if r < 1e-6:
        return 0.0
    return (dx * c.x + dy * c.y) / r


def _seed_footprint(s):
    """The seed's REAL outline, moved so its bottom-left corner sits at (0, 0).

    A seed measured as a cut-corner outline uses that outline; a plain square or
    rectangle uses its L x W box. Either way this is the footprint the stone
    actually has — the packer never invents a cut.
    """
    from shapely import affinity
    from shapely.geometry import Polygon as ShPoly

    poly = s.get("poly")
    if poly:
        g = ShPoly(poly)
        if not g.is_valid:
            g = g.buffer(0)
        if not g.is_empty and g.area > 0 and g.geom_type == "Polygon":
            x0, y0 = g.bounds[0], g.bounds[1]
            return affinity.translate(g, -x0, -y0)
    w = float(s.get("L") or s.get("w") or 0.0)
    h = float(s.get("W") or s.get("h") or 0.0)
    if w <= 0 or h <= 0:
        return None
    return ShPoly([(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)])


# Rotation is allowed for every seed — squares, rectangles and cut/trimmed alike.
# Turning a stone on the plate is a real operation; MIRRORING one is not, and
# affinity.rotate() cannot produce a mirror, so every orientation reached here is
# physically buildable.
#
# The rule from the shop floor is "clockwise only". That does NOT narrow this
# tuple: a 90 degree clockwise turn is a 270 degree anticlockwise one, so turning
# only clockwise still reaches all four orientations. Direction of travel does not
# constrain where a stone ends up — only which final orientations are permitted
# does, and all four are.
#
# 180 is tried straight after 0 on purpose: a cut corner and its neighbour's cut
# corner only nest when one of them is turned to face the other.
#
# HISTORY, so this is not flip-flopped again without cause. This was briefly
# (0,) after a real plate showed 7 of 11 cut seeds facing left when every real
# stone faced right. Locking to 0 hid that, and happened to pack better too:
#
#   rotation allowed   3 plates   84.0 / 67.7 / 11.4 %   run avg 54.4%
#   no rotation        2 plates   83.9 / 79.1 %          run avg 81.5%
#
# But 0-only treated the symptom. The cause is that the sheet cannot say which
# side the cut is on, so the outline is rebuilt from the L1/W2/L3/W4 ORDER alone
# and a mirrored reading is indistinguishable from a correct one. The datasheet
# is gaining an explicit cut-side column; once orientation is stated rather than
# inferred, rotation is safe and the packer keeps the freedom it needs.
#
# UNTIL that column is imported, cut seeds can still be turned to face the wrong
# way — the run-average figures above are what that costs.
ENHANCED_ANGLES = (0, 180, 90, 270)
NEST_STEP = 0.25          # mm — how finely a seed is slid left to close a gap
ROW_PROBE = 1.0           # mm — how far to step up when a row height fits nothing
RIM_EPS = 0.05            # mm — start this far inside the chord, so a corner
                          # lying exactly on the circle is not rejected (the disc
                          # is a 180-gon, marginally inside the true circle)
ROW_TOL = 0.15            # mm — how much taller than its row a seed may stand
SWEEP_ANCHORS = 48        # max pocket corners the sweep-up pass probes

# Who wins a seat when a cut stone and a plain one both fit. BOTH are tried on
# every plate and the better result is kept — see enhanced_plate_job.
#
#   "cut-first"   — a cut stone takes the rim seat that opens a row, so the cut
#                   pile drains a few per plate. Packs more stones in, but spends
#                   crosses in the middle of the plate where they leave a notch.
#   "plain-first" — a plain stone wins any tie. Fewer stones, far less waste.
#
# Measured on the reference plate, and the reason neither is hard-coded:
#
#   cut-first     42 seats  84.90%  11 cut used  10 unbuildable seats  24.6 mm2
#   plain-first   39 seats  84.37%   4 cut used   2 unbuildable seats   2.3 mm2
#
# Coverage alone would pick cut-first; buildable area picks plain-first. Which
# one wins depends on the mix on the day, so the packer runs both.
CUT_POLICIES = ("cut-first", "plain-first")

# How each row is laid. CENTRE-OUT only: rows start at the middle of the plate
# and grow both ways, so what is left over is shared between the two rims.
#
# The old "left" mode opened every row at the left chord and filled across,
# which pushed all the slack to one side — measured on the Ø80 reference plate,
# 27.99 mm of clear rim on the left against 30.06 mm on the right. Centre-out
# balances that to 29.13 against 29.09, and a symmetric plate is what the shop
# floor wants to work from.
#
# It is also better on the numbers, once the whole run is counted:
#
#   centre   plate 1: 40 seats 84.63%  7 cut  3 unbuildable | run: 35 cut, 27 bad
#   left     plate 1: 38 seats 83.84%  1 cut  0 unbuildable | run: 35 cut, 28 bad
#
# Left-to-right keeps plate 1 spotless only by pushing the cut stones onto plate
# 2, where they cost more. Over three plates the two place the same 35 cut stones
# and centre-out ends one unbuildable seat ahead.
#
# "left" is still implemented and can be put back here as a candidate; the packer
# tries every entry in this tuple and keeps the best-scoring plate.
FILL_DIRECTIONS = ("centre",)

# Where the first row's baseline sits, as an offset above the bottom of the
# plate. Rows stack from there, so this is the PHASE of the row grid against the
# circle: it decides which chords every row lands on, and a chord 1 mm higher can
# be several mm wider. Packing used to start hard at -R, which is an arbitrary
# phase, not a good one.
#
# On the Ø80 reference plate the phase alone moved coverage across a 7.7-point
# band — 76.3% at its worst, 84.0% at its best, with the shipped -R landing at
# 78.7%. It is far too big a lever to leave to chance, and the best phase depends
# on the seed mix, so it cannot simply be hard-coded either. enhanced_plate_job
# therefore packs the plate once per phase and keeps the best result.
#
# Coarse sweep first, then a refine step either side of the winner. Rows run
# about 9 mm tall, so phases beyond that repeat what a lower one already tried.
#
# The step is COARSE on purpose. Every phase is packed once per cut policy and
# once per fill direction, so the phase count multiplies by four. With real cut
# outlines a single pack costs about 30 s — polygon-against-polygon tests are far
# dearer than box-against-box — and a seven-phase sweep took 946 s a plate. Four
# phases plus the refine step below covers the same 0-6 mm range and brings that
# back to roughly a third.
ROW_PHASES = (0.0, 2.0, 4.0, 6.0)
ROW_PHASE_REFINE = 1.0

# How a seat picks between stones that fit it equally well.
#
#   "compact"  the original: closest fit, cut direction breaks the tie.
#   "area"     among equally good fits, take the stone that COVERS MORE.
#
# Neither wins everywhere, which is why both are swept and the better result is
# kept. On a pool of one size "compact" leads (84.59% vs 82.33% on 74 stones);
# on a mixed pool "area" leads (83.77% vs 82.83% on 163). The mixed case is the
# one that matters in practice, and it also fixes a wrong behaviour: under
# "compact" alone, ADDING stock lowered the plate — 84.59% fell to 82.83% when
# 89 narrow stones joined 74 wide ones, because the greedy spent seats on narrow
# stones that fit the seat but covered less. "area" reverses that (+1.44).
#
# Two other candidates were measured and rejected: penalising a placement that
# leaves a gap too narrow for any stone ("fit", 81.99%) and combining it with
# area (81.93%). Both LOWERED coverage — avoiding a dead remainder costs more
# mid-row than the rim scrap it saves.
SEAT_SCORES = ("compact", "area")

# How close to the chord a seat must be to count as a RIM seat. Cut/trimmed
# stones are steered here: against the curve a ground corner costs nothing,
# while in open plate it leaves a notch a flat neighbour cannot close, and the
# seat is rejected on the floor.
#
# 8 mm, not wider. Measured on a 163-stone pool (56 of them cut):
#     0 mm  (rule off)  48 seats  83.99%  7 cut stones
#     8 mm              51 seats  85.85%  18 cut stones, 6 per side
#    14 mm              43 seats  77.93%  18 cut stones, 5 per side
# Past about 8 mm the rule starts claiming seats that are not really against
# the curve, and a cut stone there wastes more plate than it saves.
RIM_SEAT = 8.0

# Seat cut stones at both rims BEFORE filling the row. Measured far worse than
# filling whole-first and capping afterwards; see seed_row_ends().
CUTS_FIRST = False

# Edge utilisation first: let cut/trimmed stones win the rim seats during the
# fill, and close that side of the row behind them. Fills every rim seat outside
# the centre band (12 of 12 on a 90 mm plate) for about 4 points of coverage.
EDGE_FIRST = False

# The rows across the middle of the plate are its widest and most useful part,
# so they stay for whole stones — cut ones are pushed to the rows above and
# below. Half-height of that protected band, in mm.
CENTRE_BAND = 10.0

# Most plate a cut stone's missing corner may waste INSIDE the circle, mm2.
# Above this the cross is not following the rim and the seat is unbuildable.
CUT_NOTCH_MAX = 1.0


def _interior_waste(placed, disc):
    """What a layout wastes because a cross has nothing to face.

    Returns ``(notch_area, stone_count, stone_area)`` — the open notch beside
    such stones, how many there are, and how much stone is sitting in those
    unbuildable seats.

    A cut stone's missing corner has to go somewhere. Against the rim it costs
    nothing — that crescent was unusable anyway. Against another cross it costs
    nothing either, because the two sit flush. Against a FLAT neighbour it leaves
    a notch no stone can enter, and the shop floor cannot build that seat.
    """
    from shapely.geometry import Polygon as ShPoly, box as shbox
    from shapely.ops import unary_union

    if not placed:
        return 0.0, 0, 0.0
    occ = unary_union([ShPoly(p["poly"]).buffer(0) for p in placed])
    waste, n, stone = 0.0, 0, 0.0
    for p in placed:
        g = ShPoly(p["poly"]).buffer(0)
        void = shbox(*g.bounds).difference(g)
        if void.is_empty or void.area < 0.05:
            continue                                  # a plain rectangle
        inside = void.intersection(disc)
        if void.area - inside.area > void.area * 0.5:
            continue                                  # mostly past the rim
        open_part = inside.difference(occ)             # not taken by a neighbour
        if open_part.area >= void.area * 0.25:
            waste += open_part.area
            stone += g.area
            n += 1
    return waste, n, stone


def _pack_once(args, y0=None, policy="cut-first", fill="left", seat="compact"):
    """ONE complete packing run for MAX COVERAGE. Returns (placed, fill_pct).

    Draws nothing and mutates no caller state, so it is safe to call repeatedly
    on the same pool — enhanced_plate_job runs it once per candidate row phase
    and renders only the best result.

    Seeds arrive already cut or trimmed on the shop floor, so this packer never
    cuts anything. Each seed is placed at its true measured footprint or not at
    all; one that will not fit in any orientation is left for the next plate.
    That is why the rim stays ragged rather than being shaved flush.

    Seats are not a fixed grid. A row opens at the height of the seed that starts
    it, each seed is laid at its OWN width, and every seed is slid left until it
    touches its neighbour — the slide is what lets two opposing cut corners nest
    instead of each leaving a triangle of scrap.

    `args` = (real, pi, plate_d, R, min_size, path); `y0` is the absolute y of
    the first row's baseline, None meaning the bottom of the plate; `policy`
    decides who wins a seat when a cut stone and a plain one both fit:

      "cut-first"   — a cut stone takes the rim seat that opens a row, so the
                      cut pile drains a few per plate
      "plain-first" — a plain stone wins any tie, so crosses are not spent in
                      the middle of the plate where they leave a notch

    `fill` is the direction each row is laid:

      "left"   — open at the left chord and fill across, as it always has
      "centre" — start at the middle of the plate and grow both ways, so a row
                 ends ragged at both rims instead of flush left and ragged right
    """
    real, pi, plate_d, R, min_size, path = args
    P.PLATE_D = plate_d
    from shapely import STRtree, affinity
    from shapely.geometry import Point, Polygon as ShPoly, box as shbox
    from shapely.ops import unary_union

    disc = Point(0.0, 0.0).buffer(R, resolution=180)
    # The disc is a 180-gon inscribed in the true circle, so a box that clears
    # this radius is inside the polygon too. RIM_EPS keeps the analytic test on
    # the safe side of that difference.
    RSQ = (R - RIM_EPS) ** 2
    if not real:
        return [], 0.0

    defH = round((P.T_LO + P.T_HI) / 2.0, 3)
    EPS = 1e-6
    # "Distance between seeds" from the criteria form, in mm. Kept between seeds
    # only — the clear ring around the plate is the MARGIN, already taken out of
    # R before this runs. 0 packs edge to edge, as before.
    clear = max(0.0, float(getattr(P, "CLEARANCE", 0.0) or 0.0))
    # Narrowest stone in the pool. A leftover slimmer than this can never be
    # seated, which is what makes the SQUEEZE below worth attempting.
    narrowest = min((min(float(s.get("L") or 99.0), float(s.get("W") or 99.0))
                     for s in real), default=0.0)
    # Where each half of a centre-out row stops. The two halves grow towards each
    # other and must not touch, so the middle needs the gap as well: the
    # rightward half owns x >= +half, the leftward half x <= -half, leaving
    # exactly `clear` across the centre line and the same margin at both rims.
    #
    # Getting this wrong is not a cosmetic error. With both halves stopped at 0
    # the first leftward seed of every row landed flush against the first
    # rightward one, free() refused it for being 0 mm away when `clear` mm were
    # required, and — since no orientation of any seed could ever satisfy that
    # seat — the whole left side of the row was marked dead. Rows collapsed into
    # short fragments: at 0.5 mm a Ø90 plate fell to 19 stunted rows, 31 seats,
    # 68.10%, against 84.63% at 0 mm where the bug cannot bite.
    half = clear / 2.0

    shapes, cutdirs, poses = {}, {}, {}
    for s in real:
        g = _seed_footprint(s)
        if g is not None:
            shapes[id(s)] = g
            cutdirs[id(s)] = _cut_direction(g)
            # A seed only ever has these four orientations, and scan() reaches
            # for them once per seat. Rotating on demand redid the same few
            # hundred rotations ten thousand times a plate; turning each seed
            # once here and keeping its size alongside cuts a pack by a fifth.
            pl = []
            for deg in ENHANCED_ANGLES:
                # ROTATION ONLY, never a mirror: affinity.rotate preserves
                # handedness, matching how a seed can actually be laid down.
                rg = affinity.rotate(g, deg, origin="centroid") if deg else g
                b = rg.bounds
                pl.append((deg, rg, b[2] - b[0], b[3] - b[1]))
            poses[id(s)] = pl
    queue = [s for s in real if id(s) in shapes]
    # Tall-first: the seed that opens a row sets that row's height, so starting
    # with the tallest stops a row being opened too short to be reused.
    #
    # Then WIDEST first among equal heights. Ties were previously broken by
    # whatever order the pool arrived in, and with far more seeds available than
    # one plate holds that choice is a real lever — spending a row's width on
    # fewer, wider seeds leaves less end-of-row remainder. Worth 1.6 points on a
    # Ø80 plate (77.08% to 78.71%) for a change of sort key alone.
    #
    # ASSUMED corners go last. A stone whose datasheet left the cross corner
    # blank is carrying a guess — LEFT-TOP — and a guess is right only about two
    # thirds of the time, because rotation turns LEFT-TOP into RIGHT-BOTTOM but
    # can never reach LEFT-BOTTOM or RIGHT-TOP, which are mirror images. Placing
    # the declared stones first means a plate that fills on known-good data never
    # spends a guessed one at all.
    queue.sort(key=lambda s: (1 if s.get("corner_assumed") else 0,
                              -(shapes[id(s)].bounds[3] - shapes[id(s)].bounds[1]),
                              -(shapes[id(s)].bounds[2] - shapes[id(s)].bounds[0])))

    placed, occ, used = [], [], set()
    srcs = []          # seed behind each placement, so one can be undone

    # Spatial index over what is already placed. free() is called thousands of
    # times — every probe, and every 0.25 mm step of every nesting slide — and
    # testing each call against all 40+ placed seeds made a plate take 25 s.
    # The index narrows it to the handful that could possibly be in the way.
    tree = [None]

    def reindex():
        tree[0] = STRtree(occ) if occ else None

    def free(g):
        """Wholly inside the plate, and at least `clear` mm from every neighbour."""
        # Cheap analytic rim test first. disc.contains() walks a 180-gon and is
        # called tens of thousands of times a pack; the four corners of the
        # bounding box against R settles almost every case without it, and a box
        # inside the circle guarantees the stone inside it is too.
        bx0, by0, bx1, by1 = g.bounds
        far = max(bx0 * bx0, bx1 * bx1) + max(by0 * by0, by1 * by1)
        if far > RSQ:
            # A corner of the BOX is outside — the stone itself may still be in
            # (a ground-off corner), so fall back to the exact test.
            if not disc.contains(g):
                return False
        t = tree[0]
        if t is None:
            return True
        probe = g.buffer(clear) if clear > 0.0 else g
        for i in t.query(probe):
            o = occ[i]
            if clear > 0.0:
                if g.distance(o) < clear - EPS:
                    return False
                continue
            # Seeds are laid touching, so `intersects` is true for every
            # neighbour and the old test paid for a full polygon intersection on
            # each one. Overlapping BOXES are a prerequisite for overlapping
            # areas, so reject on the boxes first — that settles a touching
            # neighbour with four comparisons instead.
            ob0, ob1, ob2, ob3 = o.bounds
            if (min(bx1, ob2) - max(bx0, ob0) <= EPS
                    or min(by1, ob3) - max(by0, ob1) <= EPS):
                continue
            if g.intersects(o) and g.intersection(o).area > EPS:
                return False
        return True

    def slide_left(g, limit=None):
        """Nudge a seed left while it stays legal — this is the nesting step.

        `limit` stops the seed's left edge going past a line. Centre-out needs
        it: the first stone of a row has nothing to its left, so without a stop
        it slides the full width of the plate to the rim — which defeats the
        point of starting at the centre AND costs hundreds of collision tests,
        since every 0.25 mm step is a full free() check.
        """
        cur = g
        while True:
            if limit is not None and cur.bounds[0] - NEST_STEP < limit:
                return cur
            nxt = affinity.translate(cur, -NEST_STEP, 0.0)
            if not free(nxt):
                return cur
            cur = nxt

    def slide_right(g, limit=None):
        """The mirror of slide_left, for a row growing leftwards from the middle.
        `limit` caps the seed's RIGHT edge."""
        cur = g
        while True:
            if limit is not None and cur.bounds[2] + NEST_STEP > limit:
                return cur
            nxt = affinity.translate(cur, NEST_STEP, 0.0)
            if not free(nxt):
                return cur
            cur = nxt

    def record(s, deg, g):
        """Commit a placement. Used by both the row sweep and the sweep-up pass,
        so the two can never drift in what they store."""
        used.add(id(s))
        srcs.append(s)
        occ.append(g)
        reindex()
        bx0, by0, bx1, by1 = g.bounds
        rp = g.representative_point()
        placed.append({
            "stock": s["stock"], "cts": s.get("cts", 0.0),
            "L": round(bx1 - bx0, 1), "W": round(by1 - by0, 1),
            "H": s.get("H", defH),
            # The stone's measurement from the import, for the seed list.
            "rawL": s.get("L"), "rawW": s.get("W"),
            "x": bx0, "y": by0, "w": bx1 - bx0, "h": by1 - by0, "angle": deg,
            "kind": "real",
            "poly": [(round(px, 3), round(py, 3)) for px, py in g.exterior.coords],
            "area": g.area,
            # No "clipped"/"nomarea": nothing is ever cut, so there is no trim to
            # report and dim_rows() renders these as plain real seeds.
            "irregular": bool(s.get("poly")),
            "lx": rp.x, "ly": rp.y,
        })

    def scan(y, x, row_h, allow_taller, going_left=False, want_cut=None,
             rim_seed=False):
        """Best seed for the seat at (x, y), or None. Returns (key, seed, deg, poly).

        `x` is the seat's NEAR edge: its left edge when the row grows rightwards,
        its right edge when the row grows leftwards from the middle of the plate.
        """
        best = None
        for s in queue:
            if id(s) in used:
                continue
            g0, cut0 = shapes[id(s)], cutdirs[id(s)]
            # WHOLE-first, then CAP the ends with cut stones. A row filled with
            # both at once lets a cut stone win an ordinary seat and close that
            # side early, which cost 5.8 points of coverage. Filling with whole
            # stones and capping afterwards puts the ground corners in the
            # crescent no rectangle can reach — the space they are FOR.
            if want_cut is True and cut0 is None:
                continue
            if want_cut is False and cut0 is not None:
                continue
            for deg, rg, ww, hh in poses[id(s)]:
                if row_h > 0.0 and hh > row_h + ROW_TOL and not allow_taller:
                    continue
                # The binding corner is on whichever of THIS seed's edges is
                # nearer the rim, which depends on its own height, not the row's.
                y_out = max(abs(y), abs(y + hh))
                if y_out >= R:
                    continue
                chord = math.sqrt(R * R - y_out * y_out) - RIM_EPS
                # No cheap width pre-test here on purpose. Rejecting a seat
                # because the seed's BOUNDING BOX overruns the far chord throws
                # away legal placements of cut seeds: the ground-off corner means
                # the box crosses the chord while the stone itself is still
                # inside. free() tests the true outline, so let it decide.
                rb = rg.bounds
                # Centre-out keeps each half on its own side of the middle: a
                # stone growing rightwards may nest back toward x=0 but not past
                # it, and vice versa. Left-to-right has no such stop — its stones
                # nest all the way back to whatever is already placed.
                # rim_seed places the stone FLUSH to the chord and leaves it
                # there. The cursor `x` is an edge — the right edge going left,
                # the left edge going right — so seating at the rim has to be
                # computed from the stone's own width, and it must NOT then be
                # slid back toward the middle, which is the whole point.
                bw = rb[2] - rb[0]
                if going_left:
                    # Right edge on the cursor, then nudged back toward the middle.
                    x_at = (-chord + bw) if rim_seed else min(x, chord)
                    g = affinity.translate(rg, x_at - rb[2], y - rb[1])
                    if not free(g):
                        continue
                    if not rim_seed:
                        g = slide_right(g, -half if fill == "centre" else None)
                else:
                    x_at = (chord - bw) if rim_seed else max(x, -chord)
                    g = affinity.translate(rg, x_at - rb[0], y - rb[1])
                    if not free(g):
                        continue
                    if not rim_seed:
                        g = slide_left(g, half if fill == "centre" else None)

                # Plate actually LOST by taking this seat: the strip consumed
                # along the row, clipped to the plate, minus the seed itself.
                # Zero for a rectangle laid flush. This is what makes seeds nest:
                # two cut seeds sit flush when one is turned 180 degrees, and the
                # notch between them disappears from this measure.
                # The strip runs from the PREVIOUS seed to this one. For the seed
                # that OPENS a row there is no previous seed, and measuring from
                # the cursor (still at -R) charged it for the whole crescent
                # beside it — a cost that grows with the seed's height, which let
                # a 90-degree rotation win the opening slot and set the row 2 mm
                # taller than it needed to be. Every shorter seed in that row then
                # left a band above it.
                if going_left:
                    lo, hi = g.bounds[0], (g.bounds[2] if row_h <= 0.0 else x)
                else:
                    lo, hi = (g.bounds[0] if row_h <= 0.0 else x), g.bounds[2]
                sx0, sx1 = min(lo, hi), max(lo, hi)
                # Clipping the strip to the plate only matters when it actually
                # reaches the rim. Inside the circle its area is just width x
                # height, and skipping the clip removes one polygon intersection
                # per candidate seat — the single hottest call in the packer.
                if max(sx0 * sx0, sx1 * sx1) + max(y * y, (y + hh) ** 2) <= RSQ:
                    strip_area = (sx1 - sx0) * hh
                else:
                    strip_area = shbox(sx0, y, sx1, y + hh).intersection(disc).area
                lost = max(0.0, strip_area - g.area)
                out = _outward_score(g, cut0, deg)
                gap = max(0.0, row_h - hh) if row_h > 0.0 else 0.0
                # A seed lying flat — its shorter side as the height. Only that
                # orientation may open a row: standing one on its long side sets
                # the row taller than anything else will fill, and every later
                # seed then leaves a band above it.
                lying_flat = hh <= min(g0.bounds[2] - g0.bounds[0],
                                       g0.bounds[3] - g0.bounds[1]) + 0.05
                # A stone whose cross corner was ASSUMED is a last resort at
                # every seat, not merely later in the queue. Sorting the queue
                # only breaks ties — scan() picks the best-scoring stone for each
                # seat, so an assumed one still won seats while declared stones
                # were going spare. Leading the key with this makes the rule
                # absolute: an assumed stone is chosen only when no declared one
                # fits the seat at all.
                # A row's height is fixed by whatever opens it, and every row
                # above sits on that line — so a stone standing on its LONG side
                # opens a 13.9 mm row and knocks the whole plate out of square.
                # Measured: row heights ranged 7.8-13.9 mm before this, 8.9-9.9
                # after. Uniform rows matter more to the floor than the ~1 point
                # of coverage a tall opener occasionally buys.
                if row_h <= 0.0 and not lying_flat:
                    continue
                # Is this seat against the rim? Centre-out grows each row from
                # the middle, so the rim seats are the LAST of each half, not the
                # first — how much room is left to the chord is what says so.
                # Both halves qualify, which is how cut stones reach BOTH sides;
                # the old test (row_h <= 0) fired on the first seat of the row,
                # which under centre-out is the CENTRE, so cut stones were being
                # pushed into open plate and rejected. 2 of 56 were being used.
                _rem = (g.bounds[0] + chord) if going_left else (chord - g.bounds[2])
                _mid = abs(y + hh / 2.0) < CENTRE_BAND
                # -1 outranks a plain stone (0) outright. Merely tying is not
                # enough: a cut stone's notch counts as `lost`, so on any tie the
                # plain rectangle wins and the cross never reaches the rim.
                if cut0 is None:
                    cutrim = 0
                elif _rem < RIM_SEAT and out > 0.0 and not _mid:
                    # The cut must genuinely follow the curve. `out > 0` only
                    # says the ground corner points outward-ish; it still allows
                    # a placement whose missing corner sits INSIDE the plate,
                    # leaving the triangular notch beside a neighbour that the
                    # floor cannot build. Measure the notch instead of trusting
                    # the direction: against the rim it is ~0, facing in it is
                    # the whole triangle.
                    if _wasted_area(g, disc) > CUT_NOTCH_MAX:
                        continue
                    cutrim = -1
                else:
                    # BANNED, not merely penalised. A ground corner away from the
                    # rim faces a flat neighbour, leaving a notch nothing can
                    # close — the floor rejects the seat. Penalising was not
                    # enough: where no whole stone fitted, the penalised cut
                    # stone was still the best candidate and went in anyway, six
                    # times on one plate. Leaving the seat empty is cheaper.
                    continue
                # EDGE UTILISATION: with cut stones allowed into the fill they
                # win rim seats outright (-1 beats a plain stone's 0). Every rim
                # seat outside the centre band then takes one — 12 of the 12
                # such seats a Ø90 plate has. The cost is ~4 points of coverage,
                # paid deliberately: a ground stone that never leaves the drawer
                # is 100% waste, and the rim is the only place it can go.
                risky = 1 if s.get("corner_assumed") else 0
                if (policy == "cut-first" and row_h <= 0.0
                        and cut0 is not None and out > 0.0 and lying_flat):
                    # ROW-END SEAT. The first seat of a row sits against the rim,
                    # and that is where a ground corner earns its keep. Cut seeds
                    # take it ahead of a rectangle so they drain a few per plate,
                    # rather than piling up until a plate holds nothing else.
                    #
                    # Height comes BEFORE the cut direction here. This seat sets
                    # the row's height, and every later seed in the row must fit
                    # under it — so an orientation standing the seed on its long
                    # side makes the whole row too tall and leaves a band above
                    # every neighbour. Ranking only on the outward cut chose
                    # exactly that: an 8.88 mm seed turned 90 degrees opened a row
                    # at 11.12 mm and cost 55 mm2 in one stripe.
                    key = (risky, -1.0, -out, round(lost, 2))
                else:
                    # Mid-row, FILLING THE ROW'S HEIGHT matters more than which
                    # way a cut points. A seed shorter than its row leaves a
                    # strip above it that no later row can reach — the horizontal
                    # bands between rows — and every orientation is available to
                    # close it, since turning a seed 90 degrees swaps which of
                    # its sides is the height. Ranking the cut direction first
                    # left those bands open for the sake of a cut that, away from
                    # the rim, has no curve to follow anyway.
                    #
                    # Under "plain-first" a plain stone also wins any tie against
                    # a cut one. A cut stone put here has its cross facing a flat
                    # neighbour, which leaves a notch nothing can fill and a seat
                    # the shop floor cannot build.
                    # Under "area", the stone that covers more wins any tie the
                    # fit and the row height leave open. Placed AFTER lost/gap so
                    # it never overrides a tighter fit or a better-filled row —
                    # it only decides between stones that were already equal, and
                    # there the wider one is simply more plate covered.
                    bulk = -g.area if seat == "area" else 0.0
                    key = ((risky, cutrim, round(lost, 2), round(gap, 2),
                            1 if cut0 is not None else 0, bulk, -out)
                           if policy == "plain-first"
                           else (risky, cutrim, round(lost, 2), round(gap, 2), bulk, -out))
                if best is None or key < best[0]:
                    best = (key, s, deg, g)
        return best

    y = -R if y0 is None else y0
    guard = 0
    while y < R - 0.5 and guard < 400:
        guard += 1
        if all(id(s) in used for s in queue):
            break
        # CENTRE-OUT lays each row from the middle of the plate outwards, filling
        # rightwards and leftwards in turn, so a row ends ragged at BOTH rims
        # instead of flush left and ragged right. LEFT-TO-RIGHT opens each row at
        # the left chord and fills across.
        #
        # Both are packed on every plate and the better one is kept — the row
        # direction changes which chord each row is anchored to, and which wins
        # depends on the seed mix.
        xr = half if fill == "centre" else -R
        xl = -half              # only used by centre-out, growing leftwards
        row_h = 0.0
        dead = {False: False, True: False}   # has each side run dry?
        n0 = len(placed)        # first seat of THIS row, for the squeeze below

        def seed_row_ends():
            """Seat a cut/trimmed stone at BOTH rims before the row is filled.

            Cut stones are full-size stones with one corner ground off, so they
            need a real seat, not the sliver a finished row leaves — capping
            afterwards placed 2 per plate out of 56 available. Seated first they
            take the seat they are actually good at: against the curve, where the
            ground corner follows the rim instead of wasting plate.

            The rows across the middle are skipped. That is the widest, most
            useful band and belongs to whole stones.

            Returns True if either end was seated, which suppresses the squeeze —
            a row already anchored at both rims has nothing to slide.
            """
            nonlocal row_h, xl, xr
            # OFF by default. Seating the rims before the row is filled fixes the
            # row height from a rim stone and leaves a gap between each anchor
            # and the centre fill: measured 31 seats / 52.28% against 47 / 84.17%
            # for filling whole-first. Kept because the idea is sound in
            # principle and may pay once smaller stones are stocked.
            if not CUTS_FIRST:
                return False
            if abs(y + (row_h or 9.0) / 2.0) < CENTRE_BAND:
                return False
            seated = False
            for going_left in (False, True):
                yout = max(abs(y), abs(y + (row_h or 9.0)))
                if yout >= R:
                    continue
                chord = math.sqrt(R * R - yout * yout) - RIM_EPS
                best = scan(y, 0.0, row_h, False, going_left,
                            want_cut=True, rim_seed=True)
                if not best:
                    continue
                _key, s, deg, g = best
                record(s, deg, g)
                row_h = max(row_h, g.bounds[3] - y)
                if going_left:
                    xl = min(xl, g.bounds[0] - clear)
                else:
                    xr = max(xr, g.bounds[2] + clear)
                seated = True
            return seated

        def swap_row(n0):
            """Trade one stone in the finished row for a different-width one so
            that a further stone fits — the move a greedy packer can never make.

            The packer commits a seat the moment it fills it and never looks
            back, so a row can end with, say, 7 mm spare while carrying a 13 mm
            stone that a narrower one would have served just as well. Swapping
            the two frees enough width for another stone, and the stone gained is
            worth more than the width given up.

            Only applied when it PAYS: width(new) > width(out) - width(in).
            Measured on a 163-stone pool: three rows qualified, +129 mm2, about
            +2.6 coverage points.
            """
            row = placed[n0:]
            if len(row) < 2 or row_h <= 0.0:
                return False
            yout = max(abs(y), abs(y + row_h))
            if yout >= R:
                return False
            chord = math.sqrt(R * R - yout * yout) - RIM_EPS
            lo = min(p["x"] for p in row)
            hi = max(p["x"] + p["w"] for p in row)
            gap = max(0.0, chord - hi) + max(0.0, lo + chord)
            if gap < 0.05:
                return False
            spare = [t for t in queue if id(t) not in used]

            def sides(t):
                """(width, height) for each orientation that fits this row."""
                L, W = float(t["L"]), float(t["W"])
                return [(a, b) for a, b in ((L, W), (W, L)) if b <= row_h + ROW_TOL]

            best = None
            for i, b in enumerate(row):
                for a in spare:
                    for wa, _ha in sides(a):
                        freed = gap + (b["w"] - wa)
                        if freed <= 0.0:
                            continue
                        for c in spare:
                            if c is a:
                                continue
                            for wc, _hc in sides(c):
                                if wc > freed:
                                    continue
                                gain = wc - (b["w"] - wa)
                                if gain > 0.05 and (best is None or gain > best[0]):
                                    best = (gain, i, a, wa, c, wc)
            if best is None:
                return False
            _gain, idx, a, wa, c, wc = best

            # Rebuild the row: same stones, one swapped, one added, laid left to
            # right from the chord. Everything is lifted first so the strip is
            # empty and each piece can be seated without fighting its neighbours.
            order = [(srcs[n0 + k], placed[n0 + k]["w"]) for k in range(len(row))]
            order[idx] = (a, wa)
            order.append((c, wc))
            # Cut stones must finish at the ENDS of the rebuilt row. The added
            # stone goes on last, so a cross that used to be outermost would end
            # up with a neighbour beyond it — stranded against a flat face, and
            # rejected on the floor.
            _cuts = [t for t in order if t[0].get("poly")]
            _whole = [t for t in order if not t[0].get("poly")]
            if _cuts:
                order = _cuts[:1] + _whole + _cuts[1:]
            for k in range(len(placed) - 1, n0 - 1, -1):
                used.discard(id(srcs[k]))
                placed.pop(k)
                occ.pop(k)
                srcs.pop(k)
            reindex()

            x = -chord
            for t, w in order:
                g0 = shapes[id(t)]
                pick = None
                for deg, rg, ww, hh in poses[id(t)]:
                    if abs(ww - w) < 0.01 and hh <= row_h + ROW_TOL:
                        pick = (deg, rg)
                        break
                if pick is None:
                    continue
                deg, rg = pick
                rb = rg.bounds
                g = affinity.translate(rg, x - rb[0], y - rb[1])
                if not free(g):
                    continue
                # The rebuild seats stones directly, so scan()'s cut rules do not
                # apply here — re-check them. Without this a rebuilt row could
                # carry a cross facing a flat neighbour, which is exactly what
                # appeared beside seats 43 and 5.
                if t.get("poly") and _wasted_area(g, disc) > CUT_NOTCH_MAX:
                    continue
                record(t, deg, g)
                x = g.bounds[2] + clear
            return True

        def cap_row():
            """Cap both ends of the FINISHED row with cut/trimmed stones.

            Run last, once the row can no longer move or grow, so a cross is
            always the outermost stone on its side and can never be stranded
            mid-row. The rows across the middle are skipped — that is the widest,
            most useful band and belongs to whole stones.
            """
            nonlocal xl, xr
            # Under EDGE_FIRST the fill already seats cut stones at the rims and
            # closes that side behind them. Capping on top of that adds a second
            # cross to a side that has moved on, which is how three ended up
            # mid-row. One mechanism or the other, never both.
            if EDGE_FIRST:
                return
            if row_h <= 0.0 or abs(y + row_h / 2.0) < CENTRE_BAND:
                return
            for going_left in (False, True):
                best = scan(y, xl if going_left else xr, row_h, False,
                            going_left, want_cut=True)
                if not best:
                    continue
                _key, s2, deg, g = best
                record(s2, deg, g)
                if going_left:
                    xl = min(xl, g.bounds[0] - clear)
                else:
                    xr = max(xr, g.bounds[2] + clear)

        def fill_row():
            """Fill the current row with WHOLE stones until neither side takes
            another seat."""
            nonlocal row_h, xl, xr
            while True:
                # Level rows only. A taller seed is never admitted, even when the
                # row would otherwise end early: letting one in raises the row's
                # height, and every shorter seed already in it then sits under a
                # band that no later row can reach. Measured on a Ø80 plate that
                # traded 80.5% for 78.0% — the stretch of row left empty costs
                # less than the band.
                took = False
                for going_left in ((False, True) if fill == "centre" else (False,)):
                    # Once a side of the row has nothing left that fits, STOP
                    # scanning it. Re-scanning an exhausted side costs a full pass
                    # over the queue for every remaining seat on the other side,
                    # and that alone made a centre-out pack take 62 s against 5 s.
                    if dead[going_left]:
                        continue
                    best = scan(y, xl if going_left else xr, row_h, False,
                                going_left,
                                want_cut=None if EDGE_FIRST else False)
                    if not best:
                        dead[going_left] = True
                        continue
                    _key, s, deg, g = best
                    record(s, deg, g)
                    # Leave the requested gap before the next seat, and before the
                    # next row. free() already enforces it against every
                    # neighbour; advancing the cursors too stops the search
                    # starting inside a gap it can never use, which would
                    # otherwise cost a slide attempt for every seed.
                    if going_left:
                        xl = min(xl, g.bounds[0] - clear)
                    else:
                        xr = max(xr, g.bounds[2] + clear)
                    row_h = max(row_h, g.bounds[3] - y)
                    took = True
                    # A cut stone CLOSES its side. It earns the seat because its
                    # ground corner follows the rim; build one more stone outside
                    # it and the cross is stranded mid-row against a flat
                    # neighbour — six such seats appeared on one plate before
                    # this rule, and the floor rejects every one.
                    if EDGE_FIRST and s.get("poly"):
                        dead[going_left] = True
                if not took:
                    break

        # Cut stones claim both rims BEFORE the row is filled; whole stones
        # then fill inward between them.
        anchored = seed_row_ends()
        fill_row()
        # ---- SQUEEZE: push the finished row against one rim and refill --------
        # Centre-out leaves a little space at BOTH ends of a row, and neither
        # half is wide enough for another stone. Slid together against one side
        # they often are — one extra seat per row is worth more than the
        # symmetry, and the row is still a straight line either way.
        if row_h > 0.0 and fill == "centre" and len(placed) > n0 and not anchored:
            yout = max(abs(y), abs(y + row_h))
            if yout < R:
                chord = math.sqrt(R * R - yout * yout) - RIM_EPS
                lo = min(p["x"] for p in placed[n0:])
                hi = max(p["x"] + p["w"] for p in placed[n0:])
                lgap, rgap = lo + chord, chord - hi
                # Only worth doing when the two halves TOGETHER could seat a
                # stone that neither could alone.
                if min(lgap, rgap) > 0.01 and lgap + rgap >= narrowest:
                    shift = -lgap if lgap <= rgap else rgap
                    for i in range(n0, len(placed)):
                        occ[i] = affinity.translate(occ[i], shift, 0.0)
                        p = placed[i]
                        p["x"] += shift
                        p["lx"] += shift
                        p["poly"] = [(round(px + shift, 3), py) for px, py in p["poly"]]
                    reindex()
                    xl = min(p["x"] for p in placed[n0:]) - clear
                    xr = max(p["x"] + p["w"] for p in placed[n0:]) + clear
                    # Reopen both sides, EXCEPT one already closed by a cut
                    # stone — refilling past it is exactly what stranded crosses
                    # in the middle of a row.
                    outer_l = min(placed[n0:], key=lambda p: p["x"])
                    outer_r = max(placed[n0:], key=lambda p: p["x"] + p["w"])
                    dead = {False: bool(outer_r.get("irregular")),
                            True: bool(outer_l.get("irregular"))}
                    fill_row()
        # Trade a stone for a different width if that lets one more in.
        if row_h > 0.0 and swap_row(n0):
            pass
        # Cut stones go on LAST, into the crescent whole stones cannot reach.
        cap_row()
        y += (row_h + clear) if row_h > 0 else ROW_PROBE

    # ---- SWEEP-UP: whole seeds into the pockets the row sweep walked past -----
    # The row sweep fills strictly left to right and never returns, and a row
    # ends the moment no remaining seed fits its height — so the rest of that
    # row is abandoned even where the circle is still wide open. That left space
    # a leftover seed would have fitted: on a Ø80 plate, six of six leftovers
    # still had a legal position, all in the same abandoned stretch.
    #
    # This pass only ever ADDS a seed to a spot that is already proven free, so
    # it cannot move or displace anything the rows placed — coverage can only go
    # up. Largest-first, so a big pocket is not wasted on a small seed.
    # Searched POCKET BY POCKET, not over a blanket grid. A seed dropped into a
    # gap comes to rest against its corners, so the pocket's own bounding-box
    # corners and outline vertices are the only anchors worth testing — a 1 mm
    # sweep of the whole plate per leftover seed took 38 s a plate for the same
    # result.
    smallest = min((shapes[id(s)].area for s in queue), default=0.0)
    gap_region = disc.difference(unary_union(occ)) if occ else disc
    for _ in range(len(queue)):
        if gap_region.is_empty:
            break
        pockets = [g for g in (list(gap_region.geoms)
                               if gap_region.geom_type != "Polygon" else [gap_region])
                   if g.geom_type == "Polygon" and g.area >= smallest]
        pockets.sort(key=lambda g: -g.area)
        spare = sorted((s for s in queue if id(s) not in used),
                       key=lambda s: -shapes[id(s)].area)
        chosen = None
        for part in pockets:
            px0, py0, px1, py1 = part.bounds
            pw, ph = px1 - px0, py1 - py0
            # A pocket that snakes between seeds carries hundreds of vertices,
            # and probing every one dominated the runtime. Simplify first and cap
            # the list: a seed comes to rest against a corner, and the corners
            # that matter survive simplification.
            corners = list(part.simplify(0.4).exterior.coords)[:-1][:SWEEP_ANCHORS]
            for s in spare:
                g0 = shapes[id(s)]
                if g0.area > part.area:
                    continue                   # cannot fit in this pocket at all
                for deg, g, w, h in poses[id(s)]:
                    if w > pw + 1e-9 or h > ph + 1e-9:
                        continue
                    gb = g.bounds
                    anchors = [(px0, py0), (px1 - w, py0), (px0, py1 - h), (px1 - w, py1 - h)]
                    anchors += [(vx, vy) for vx, vy in corners]
                    anchors += [(vx - w, vy) for vx, vy in corners]
                    for ax, ay in anchors:
                        cand = affinity.translate(g, ax - gb[0], ay - gb[1])
                        if free(cand):
                            chosen = (s, deg, slide_left(cand))
                            break
                    if chosen:
                        break
                if chosen:
                    break
            if chosen:
                break
        if not chosen:
            break
        record(*chosen)
        # Subtract just the seed that was placed. Rebuilding the free region from
        # the union of every seed each round was the single largest cost.
        gap_region = gap_region.difference(
            chosen[2].buffer(clear) if clear > 0.0 else chosen[2])

    # Coverage from the UNION of what is on the plate. Summing areas would
    # double-count anything that overlapped and could report over 100%.
    covered = unary_union([ShPoly(p["poly"]).buffer(0) for p in placed]).area if placed else 0.0
    return placed, 100 * covered / (math.pi * R * R)


def enhanced_plate_job(args):
    """MAX COVERAGE — pack the plate at several row phases and keep the best.

    A single pack is one greedy sweep, and a greedy sweep is only ever as good as
    where it starts. The baseline of the first row decides which chords all the
    rows above it land on, and that alone swung the reference plate from 76.3% to
    84.0%. Rather than betting on one phase, this packs the plate once per phase
    in ROW_PHASES, refines either side of the winner, and renders the best plate.

    Both cut-seed policies are tried and the better BUILDABLE result is kept —
    coverage on its own would pick a layout whose seats the shop floor rejects.

    Every run is independent and non-destructive — nothing is carried between
    them — so the result can only be at least as good as the single run this
    replaces, at the cost of packing the plate a handful of times.

    `args` = (real, pi, plate_d, R, min_size, path).
    """
    real, pi, plate_d, R, min_size, path = args
    if not real:
        render_enhanced_circle([], [], pi, R, 0.0, path)
        return (pi, [], 0.0, round(2 * R, 4), 0.0)

    from shapely.geometry import Point
    disc = Point(0.0, 0.0).buffer(R, resolution=180)

    best = {"placed": None, "fill": -1.0, "score": -1.0, "phase": 0.0,
            "policy": CUT_POLICIES[0], "dir": FILL_DIRECTIONS[0],
            "seat": SEAT_SCORES[0], "waste": 0.0, "nwaste": 0}
    tried = set()

    def attempt(ph, policy, direction=None, seat=None):
        direction = direction or best["dir"]
        seat = seat or best["seat"]
        key = (round(ph, 3), policy, direction, seat)
        if key in tried or ph < 0.0:
            return
        tried.add(key)
        pl, f = _pack_once(args, -R + ph, policy, direction, seat)
        waste, nw, stuck = _interior_waste(pl, disc)
        # SCORE = area that can actually be BUILT. Coverage on its own prefers
        # the layout that squeezes in more stones by putting crosses against flat
        # neighbours — seats the shop floor has to reject. A rejected seat costs
        # both the notch beside it and the stone sitting in it, so both come off.
        score = (f / 100.0) * math.pi * R * R - waste - stuck
        if score > best["score"]:
            best.update(placed=pl, fill=f, score=score, phase=ph,
                        policy=policy, waste=waste, nwaste=nw)
            best["dir"] = direction
            best["seat"] = seat

    # EVERY policy gets EVERY phase. It is tempting to sweep the phases once and
    # test the other policies only near the winner — on one pool both policies
    # peaked at the same phase, so it looked free. It is not. On a 90-seed pool
    # they peak in different places, and probing the second policy at the first
    # one's phase found 82.85% with an unbuildable seat when that policy's own
    # best was 83.50% with none. The pruned search returned a plate that was
    # neither policy's best. Coverage is worth more than the seconds saved.
    for direction in FILL_DIRECTIONS:
        for seat in SEAT_SCORES:
            for policy in CUT_POLICIES:
                for ph in ROW_PHASES:
                    attempt(ph, policy, direction, seat)
    # Refine around the winner — the coarse step is wider than the difference
    # between a good phase and the best one. Only the winning combination is
    # refined; re-sweeping the losers costs a pack each for nothing.
    for d in (-ROW_PHASE_REFINE, ROW_PHASE_REFINE, -ROW_PHASE_REFINE / 2,
              ROW_PHASE_REFINE / 2):
        attempt(best["phase"] + d, best["policy"], best["dir"], best["seat"])

    placed, fill = best["placed"] or [], max(0.0, best["fill"])
    render_enhanced_circle(placed, placed, pi, R, fill, path)
    return (pi, placed, round(fill, 4), round(2 * R, 4), 0.0)


def render_circle(placed, real, pi, R, fill, path):
    """Render a whole-plate Demo Max-Fill plate: real seeds (viridis) + HYBRID
    fillers — big variable-size filler seeds (blue) and fixed 2×2 dummy seeds (red) —
    across the FULL circle. Filler kind read from p['kind'] ('big' | 'dummy')."""
    PLATE = P.PLATE_D
    big = [p for p in placed if p.get("kind") == "big"]
    small = [p for p in placed if p.get("kind") == "dummy"]
    nr = len(real)
    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    ax.add_patch(Circle((0, 0), PLATE / 2, fc="#e9e9ec", ec="#888", lw=1.5, zorder=0))
    ax.add_patch(Circle((0, 0), R, fc="none", ec="#c0392b", lw=1.3, ls="--", zorder=1))
    cmap = plt.cm.viridis
    # one PatchCollection per group -> 100x fewer draw calls than per-patch add_patch
    if small:
        ax.add_collection(PatchCollection([Rect((p["x"], p["y"]), p["w"], p["h"]) for p in small],
                          facecolor="#f4a3a3", edgecolor="#c0142c", linewidth=0.35, zorder=2))
    if big:
        ax.add_collection(PatchCollection([Rect((p["x"], p["y"]), p["w"], p["h"]) for p in big],
                          facecolor="#bcd6f0", edgecolor="#1f6fb2", linewidth=0.7, zorder=2))
    if real:
        ax.add_collection(PatchCollection([Rect((p["x"], p["y"]), p["w"], p["h"]) for p in real],
                          facecolor=[cmap(i / max(1, nr - 1)) for i in range(nr)],
                          edgecolor="white", linewidth=0.6, zorder=2))
    for p in big:                                      # label EVERY big filler with its EXACT W×H
        fs = min(5.2, max(2.6, min(p["w"], p["h"]) * 0.95))  # scale text to the smaller side
        ax.text(p["x"] + p["w"] / 2, p["y"] + p["h"] / 2, f"{p['w']:.1f}×{p['h']:.1f}",
                ha="center", va="center", fontsize=fs, color="#13507f", zorder=3)
    for i, p in enumerate(real):                       # real-seed labels
        ax.text(p["x"] + p["w"] / 2, p["y"] + p["h"] / 2,
                f"{p['stock']}\n{p['L']:.1f}×{p['W']:.1f}\nH {p['H']:.2f}",
                ha="center", va="center", fontsize=6, color="white", zorder=3)
    lim = PLATE / 2 + 4
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim + 8); ax.set_aspect("equal"); ax.axis("off")
    ds = small[0]["w"] if small else 2.0                  # uniform dummy side (= min filler size)
    ax.legend(handles=[Patch(fc="#2e86c1", label=f"REAL seeds ({nr})"),
                       Patch(fc="#bcd6f0", label=f"big fillers ({len(big)})"),
                       Patch(fc="#f4a3a3", label=f"{ds:g}×{ds:g} dummies ({len(small)})")],
              loc="lower center", bbox_to_anchor=(0.5, -0.03), fontsize=8, frameon=True, ncol=3)
    circle_area = math.pi * R * R
    covered = fill / 100.0 * circle_area
    ax.set_title(f"Mixed + hybrid fill · Plate {pi:02d} · area covered "
                 f"{covered:.0f} mm² of {circle_area:.0f} mm² ({fill:.1f}%)\n"
                 f"Ø{PLATE:g} plate · blue = big fillers (W×H) · red = {ds:g}×{ds:g} mm dummies", fontsize=10)
    fig.savefig(path, dpi=85)              # fixed limits set -> no bbox_inches='tight' rescan
    plt.close(fig)


def render_cross_circle(placed, real, pi, R, fill, path):
    """Render a CROSS-fill plate: real seeds (viridis) + big rectangle fillers (blue)
    + cross/plus seeds (orange, drawn as their two bars) + 2×2 dummies (red)."""
    PLATE = P.PLATE_D
    big = [p for p in placed if p.get("kind") == "big"]
    crosses = [p for p in placed if p.get("kind") == "cross"]
    tris = [p for p in placed if p.get("kind") == "tri"]
    irregs = [p for p in placed if p.get("kind") == "irregular"]
    small = [p for p in placed if p.get("kind") == "dummy"]
    nr = len(real)
    cmap = plt.cm.viridis
    faces = [cmap(i / max(1, nr - 1)) for i in range(nr)]
    DCOL = {"big": "#bcd6f0", "cross": "#f6c177", "tri": "#9ed99b", "irregular": "#c9a0dc", "dummy": "#f4a3a3"}
    DEDGE = {"big": "#1f6fb2", "cross": "#b9770f", "tri": "#2e8b3d", "irregular": "#7d3c98", "dummy": "#c0142c"}

    fig = plt.figure(figsize=(14.5, 9.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[9.6, 5.0], wspace=0.02)
    ax = fig.add_subplot(gs[0, 0])
    axl = fig.add_subplot(gs[0, 1]); axl.axis("off")

    ax.add_patch(Circle((0, 0), PLATE / 2, fc="#e9e9ec", ec="#888", lw=1.5, zorder=0))
    ax.add_patch(Circle((0, 0), R, fc="none", ec="#c0392b", lw=1.2, ls="--", zorder=1))
    if small:
        ax.add_collection(PatchCollection([Rect((p["x"], p["y"]), p["w"], p["h"]) for p in small],
                          facecolor="#f4a3a3", edgecolor="#c0142c", linewidth=0.35, zorder=2))
    if big:
        ax.add_collection(PatchCollection([Rect((p["x"], p["y"]), p["w"], p["h"]) for p in big],
                          facecolor="#bcd6f0", edgecolor="#1f6fb2", linewidth=0.7, zorder=2))
    cross_bars = [Rect((bx, by), bw, bh) for p in crosses for (bx, by, bw, bh) in p["bars"]]
    if cross_bars:
        ax.add_collection(PatchCollection(cross_bars, facecolor="#f6c177", edgecolor="#b9770f",
                          linewidth=0.5, zorder=2))
    if tris:                                            # right-triangle seeds (green)
        ax.add_collection(PatchCollection([MplPoly(p["tri"], closed=True) for p in tris],
                          facecolor="#9ed99b", edgecolor="#2e8b3d", linewidth=0.5, zorder=2))
    if irregs:                                          # irregular boundary polygons (purple)
        ax.add_collection(PatchCollection([MplPoly(p["poly"], closed=True) for p in irregs],
                          facecolor="#c9a0dc", edgecolor="#7d3c98", linewidth=0.5, zorder=2))
    if real:                                            # seamless zero-gap real seeds
        ax.add_collection(PatchCollection([Rect((p["x"], p["y"]), p["w"], p["h"]) for p in real],
                          facecolor=faces, edgecolor=faces, linewidth=1.0, zorder=2))

    # NUMBER real seeds 1..N (white); dummy fillers D1..Dk (white too — the "D" distinguishes).
    real_ids = set(id(p) for p in real)
    dummies = [p for p in placed if id(p) not in real_ids]
    nums = [(str(i + 1), p["x"] + p["w"] / 2, p["y"] + p["h"] / 2, p["w"] * p["h"], "white")
            for i, p in enumerate(real)]
    for k, p in enumerate(dummies, 1):
        lx = p.get("lx", p["x"] + p["w"] / 2); ly = p.get("ly", p["y"] + p["h"] / 2)
        nums.append((f"D{k}", lx, ly, p.get("area", p["w"] * p["h"]), "white"))
    _draw_plate_numbers(ax, nums)
    lim = PLATE / 2 + 3
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_aspect("equal"); ax.axis("off")
    circle_area = math.pi * R * R
    covered = fill / 100.0 * circle_area
    ax.set_title(f"Machine-Cut Fill · Plate {pi:02d} · {covered:.0f} of {circle_area:.0f} mm² covered "
                 f"({fill:.1f}%) · Ø{PLATE:g} · {nr} real + {len(dummies)} dummy fillers", fontsize=10.5)

    # ---- seed list on the right: real seeds, then dummy fillers ----
    entries = [(faces[i], "#555", f"{i + 1}.",
                f"{p['stock']}   {p['L']:.1f}×{p['W']:.1f}   H {p['H']:.2f}", "#111")
               for i, p in enumerate(real)]
    for k, p in enumerate(dummies, 1):
        kind = p.get("kind", "dummy")
        entries.append((DCOL.get(kind, "#c9a0dc"), DEDGE.get(kind, "#7d3c98"), f"D{k}",
                        f"filler   {p['w']:.0f}×{p['h']:.0f}   {p.get('area', p['w'] * p['h']):.0f} mm²", "#555"))
    _draw_legend_list(axl, f"Seeds on this plate ({nr})",
                      f"D = dummy filler ({len(dummies)})", entries)

    fig.savefig(path, dpi=125, bbox_inches="tight")
    plt.close(fig)


def render_circle_job(args):
    """Picklable wrapper so plate rendering can run in a process pool. `args` =
    (placed, real, pi, plate_d, R, fill, path). Sets the plate diameter in the worker
    (its pack_v2 globals are independent of the parent) then renders."""
    placed, real, pi, plate_d, R, fill, path = args
    P.PLATE_D = plate_d
    render_circle(placed, real, pi, R, fill, path)
    return path


def plate_job(args):
    """Picklable per-plate worker: do the (expensive) hybrid gap fill for one plate
    AND render it, so both run in parallel across the process pool. `args` =
    (real, pi, plate_d, R, min_size, path). Returns (pi, placed, fill, span, gap)."""
    real, pi, plate_d, R, min_size, path = args
    P.PLATE_D = plate_d
    big, small = hybrid_fill(real, R, min_size=min_size, step=min_size / 2.0)
    placed = list(real)
    for k, (x, y, w, h) in enumerate(big, 1):
        placed.append({"stock": f"FILL-{pi:02d}-F{k}", "cts": 0.0, "L": w, "W": h, "H": 0.0,
                       "x": x, "y": y, "w": w, "h": h, "angle": 0, "filler": True, "kind": "big"})
    for k, (x, y) in enumerate(small, 1):
        placed.append({"stock": f"FILL-{pi:02d}-D{k}", "cts": 0.0, "L": min_size, "W": min_size,
                       "H": 0.0, "x": x, "y": y, "w": min_size, "h": min_size, "angle": 0,
                       "filler": True, "kind": "dummy"})
    fillH = (round(sum(p["H"] for p in real) / len(real), 3) if real
             else round((P.T_LO + P.T_HI) / 2.0, 3))        # dummies share the real seeds' thickness
    for p in placed:
        if p.get("filler"):
            p["H"] = fillH
    fill = 100 * sum(p["w"] * p["h"] for p in placed) / (math.pi * R * R)
    span = P.span_mm(placed); gap = P.inner_gap(placed)
    render_circle(placed, real, pi, R, fill, path)
    return (pi, placed, round(fill, 4), round(span, 4), round(gap, 4))


def render_real_circle(real, pi, R, fill, path):
    """Render the ARRANGE plate: ONLY the real seeds (no dummy fill), each labelled with a
    NUMBER, plus a full seed LIST beside the plate (colour swatch + stock + size + thickness).

    Shows the two settings that shaped the layout — the MARGIN kept clear around
    the plate (shaded between the plate edge and the dashed usable circle) and the
    DISTANCE BETWEEN SEEDS — so a plate can be judged without going back to the
    criteria form. Same treatment as the Max Coverage plate.
    """
    PLATE = P.PLATE_D
    margin = max(0.0, PLATE / 2.0 - R)
    seed_gap = max(0.0, float(getattr(P, "CLEARANCE", 0.0) or 0.0))
    nr = len(real)
    cmap = plt.cm.viridis
    faces = [cmap(i / max(1, nr - 1)) for i in range(nr)]

    fig = plt.figure(figsize=(14.5, 9.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[9.6, 5.0], wspace=0.02)
    ax = fig.add_subplot(gs[0, 0])
    axl = fig.add_subplot(gs[0, 1]); axl.axis("off")

    ax.add_patch(Circle((0, 0), PLATE / 2, fc="#e9e9ec", ec="#888", lw=1.5, zorder=0))
    # Shade the MARGIN ring so the clear band reads as a deliberate setting rather
    # than space the packer failed to use.
    if margin > 0.01:
        ax.add_patch(Circle((0, 0), PLATE / 2, fc="#f6dcd7", ec="none", zorder=0.4))
        ax.add_patch(Circle((0, 0), R, fc="#e9e9ec", ec="none", zorder=0.5))
    ax.add_patch(Circle((0, 0), R, fc="none", ec="#c0392b", lw=1.2, ls="--", zorder=1))
    if margin > 0.01:
        d = 0.7071          # 45° diagonal, where seeds rarely reach
        ax.annotate(
            f"margin {margin:g} mm",
            xy=(-(R + margin * 0.5) * d, (R + margin * 0.5) * d),
            xytext=(-(PLATE / 2 + 1) * d - 12, (PLATE / 2 + 1) * d + 6),
            fontsize=9, color="#a03a2c", ha="center", va="bottom", zorder=6,
            arrowprops=dict(arrowstyle="-", color="#a03a2c", lw=0.9,
                            shrinkA=0, shrinkB=1))
    if real:
        # Seamless zero-gap look: each seat's edge painted in its own fill colour.
        ax.add_collection(PatchCollection([Rect((p["x"], p["y"]), p["w"], p["h"]) for p in real],
                          facecolor=faces, edgecolor=faces, linewidth=1.0, zorder=2))
    _draw_plate_numbers(ax, [(str(i + 1), p["x"] + p["w"] / 2, p["y"] + p["h"] / 2,
                              p["w"] * p["h"], "white") for i, p in enumerate(real)])
    lim = PLATE / 2 + 3
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_aspect("equal"); ax.axis("off")
    circle_area = math.pi * R * R
    covered = fill / 100.0 * circle_area
    ax.set_title(
        f"Arrange · Plate {pi:02d} · {nr} seeds · {covered:.0f} of {circle_area:.0f} mm² "
        f"covered ({fill:.1f}%)\n"
        f"plate Ø{PLATE:g} · margin {margin:g} mm → usable Ø{2 * R:g} · "
        f"distance between seeds {seed_gap:g} mm",
        fontsize=10.5)

    entries = [(faces[i], "#555", f"{i + 1}.",
                f"{p['stock']}   {p['L']:.1f}×{p['W']:.1f}   H {p['H']:.2f}", "#111")
               for i, p in enumerate(real)]
    _draw_legend_list(
        axl, f"Seeds on this plate ({nr})",
        f"real seeds only · {seed_gap:g} mm between seeds"
        if seed_gap > 0 else "real seeds only · seeds touching",
        entries)

    fig.savefig(path, dpi=125, bbox_inches="tight")
    plt.close(fig)


def real_only_job(args):
    """Picklable per-plate worker: render ONLY the real seeds (NO dummy/filler fill). Same
    signature/return as `plate_job` so it is a drop-in for the Arrange view.
    `args` = (real, pi, plate_d, R, min_size, path). Returns (pi, placed, fill, span, gap)."""
    real, pi, plate_d, R, min_size, path = args
    P.PLATE_D = plate_d
    placed = list(real)                                    # real seeds only — no fillers appended
    fill = 100 * sum(p["w"] * p["h"] for p in placed) / (math.pi * R * R)
    span = P.span_mm(placed); gap = P.inner_gap(placed)
    render_real_circle(real, pi, R, fill, path)
    return (pi, placed, round(fill, 4), round(span, 4), round(gap, 4))


def justify_rows(real, R, side="L"):
    """Slide each flush row of real seeds to one side of its circular chord so the
    per-row slack POOLS into one larger gap on the opposite side (instead of a thin
    unfillable sliver split both ends). Pooling past the 2 mm threshold lets the gap
    fill hold real ≥2×2 fillers → higher coverage, with NO seed moved out of the
    circle (each row's outer corners stay on/inside the boundary). Rows are grouped by
    y; seeds stay flush (no inter-seed gaps introduced)."""
    rows = {}
    for p in real:
        rows.setdefault(round(p["y"], 1), []).append(p)
    out = []
    for yk, r in rows.items():
        r = sorted(r, key=lambda p: p["x"])
        yb = max(abs(yk), abs(yk + r[0]["h"]))            # binding (outer) y of the row
        half = math.sqrt(max(0.0, R * R - yb * yb))       # chord half-width there
        tot = sum(p["w"] for p in r)
        x = -half if side == "L" else half - tot
        for p in r:
            out.append(dict(p, x=round(x, 3)))
            x += p["w"]
    return out


def cross_plate_job(args):
    """Picklable per-plate worker for the CROSS-FILL section: real seeds (per-row
    justified to pool edge slack) + IRREGULAR POLYGON dummies ONLY (no square/rectangle
    decomposition) — every gap is one boundary-conforming polygon, far fewer & larger
    dummy seeds. `args` = (real, pi, plate_d, R, min_size, path). Returns
    (pi, placed, fill, span, gap)."""
    real, pi, plate_d, R, min_size, path = args
    P.PLATE_D = plate_d
    real = justify_rows(real, R, side="L")               # pool per-row slack to one side
    placed = list(real)
    for k, (coords, area, rp) in enumerate(irregular_fill(real, R, min_irr=1.5), 1):
        xs = [c[0] for c in coords]; ys = [c[1] for c in coords]
        bx, by = min(xs), min(ys); bw, bh = max(xs) - bx, max(ys) - by
        placed.append({"stock": f"FILL-{pi:02d}-I{k}", "cts": 0.0, "L": round(bw, 1), "W": round(bh, 1),
                       "H": 0.0, "x": bx, "y": by, "w": bw, "h": bh, "angle": 0, "filler": True,
                       "kind": "irregular", "poly": coords, "area": area, "lx": rp[0], "ly": rp[1]})
    fillH = (round(sum(p["H"] for p in real) / len(real), 3) if real
             else round((P.T_LO + P.T_HI) / 2.0, 3))        # dummies share the real seeds' thickness
    for p in placed:
        if p.get("filler"):
            p["H"] = fillH
    covered = sum(p.get("area", p["w"] * p["h"]) for p in placed)   # real seeds have no 'area'
    fill = 100 * covered / (math.pi * R * R)
    m = 0.0                                                # exact span over every corner/vertex
    for p in placed:
        if p.get("kind") == "irregular":
            for cx, cy in p["poly"]:
                m = max(m, math.hypot(cx, cy))
            continue
        for cx, cy in ((p["x"], p["y"]), (p["x"] + p["w"], p["y"]),
                       (p["x"] + p["w"], p["y"] + p["h"]), (p["x"], p["y"] + p["h"])):
            m = max(m, math.hypot(cx, cy))
    span = 2 * m
    render_cross_circle(placed, real, pi, R, fill, path)
    return (pi, placed, round(fill, 4), round(span, 4), 0.0)


def prev_plate_job(args):
    """PREVIOUS Cross-Fill version (kept for side-by-side comparison): real seeds +
    SQUARE / RECTANGLE / TRIANGLE dummies (>=min_size, via `cross_fill`) — many small
    straight-edged dummies, NO irregular polygons. `args` = (real, pi, plate_d, R,
    min_size, path). Returns (pi, placed, fill, span, gap)."""
    real, pi, plate_d, R, min_size, path = args
    P.PLATE_D = plate_d
    real = justify_rows(real, R, side="L")
    big, crosses, tris, fine = cross_fill(real, R, min_size=min_size, step=0.25)
    placed = list(real)
    for k, (x, y, w, h) in enumerate(big, 1):
        placed.append({"stock": f"FILL-{pi:02d}-F{k}", "cts": 0.0, "L": w, "W": h, "H": 0.0,
                       "x": x, "y": y, "w": w, "h": h, "angle": 0, "filler": True,
                       "kind": "big", "area": w * h})
    for k, (verts, area) in enumerate(tris, 1):
        xs = [vx for (vx, vy) in verts]; ys = [vy for (vx, vy) in verts]
        bx, by = min(xs), min(ys); bw, bh = max(xs) - bx, max(ys) - by
        placed.append({"stock": f"FILL-{pi:02d}-T{k}", "cts": 0.0, "L": round(bw, 1), "W": round(bh, 1),
                       "H": 0.0, "x": bx, "y": by, "w": bw, "h": bh, "angle": 0, "filler": True,
                       "kind": "tri", "tri": verts, "area": area})
    for k, (x, y, w, h) in enumerate(fine, 1):
        placed.append({"stock": f"FILL-{pi:02d}-D{k}", "cts": 0.0, "L": round(w, 1), "W": round(h, 1),
                       "H": 0.0, "x": x, "y": y, "w": w, "h": h, "angle": 0,
                       "filler": True, "kind": "dummy", "area": w * h})
    fillH = (round(sum(p["H"] for p in real) / len(real), 3) if real
             else round((P.T_LO + P.T_HI) / 2.0, 3))
    for p in placed:
        if p.get("filler"):
            p["H"] = fillH
    covered = sum(p.get("area", p["w"] * p["h"]) for p in placed)
    fill = 100 * covered / (math.pi * R * R)
    m = 0.0
    for p in placed:
        if p.get("kind") == "tri":
            for cx, cy in p["tri"]:
                m = max(m, math.hypot(cx, cy))
            continue
        for cx, cy in ((p["x"], p["y"]), (p["x"] + p["w"], p["y"]),
                       (p["x"] + p["w"], p["y"] + p["h"]), (p["x"], p["y"] + p["h"])):
            m = max(m, math.hypot(cx, cy))
    span = 2 * m
    render_cross_circle(placed, real, pi, R, fill, path)
    return (pi, placed, round(fill, 4), round(span, 4), 0.0)


def _warm(_i=0):
    """Warm a pool worker: triggers the matplotlib import + font-cache build via a
    tiny empty render, so the first real request renders at full speed."""
    import tempfile
    render_circle([], [], 1, 43.5, 0.0,
                  os.path.join(tempfile.gettempdir(), f"_warm_{os.getpid()}.png"))
    return True


def main():
    ap = argparse.ArgumentParser(description="Demo max-fill with synthetic fillers (saved separately).")
    ap.add_argument("file", nargs="?", default="BLOCK.xlsx")
    ap.add_argument("--t-lo", dest="t_lo", type=float, default=0.67)
    ap.add_argument("--t-hi", dest="t_hi", type=float, default=0.73)
    ap.add_argument("--plate", type=float, default=90.0)
    ap.add_argument("--margin", type=float, default=3.0)
    ap.add_argument("--shape", default="all", choices=["all", "square", "rectangle"])
    ap.add_argument("--min-seed", dest="min_seed", type=float, default=2.0)
    a = ap.parse_args()

    P.T_LO, P.T_HI = a.t_lo, a.t_hi
    P.PLATE_D, P.USABLE_D = a.plate, a.plate - a.margin
    P.R = P.USABLE_D / 2.0
    P.S2 = (P.USABLE_D / math.sqrt(2)) / 2.0
    P.INSCRIBED = P.USABLE_D / math.sqrt(2)
    P.MINSEED = a.min_seed
    R = P.R
    circle_area = math.pi * R * R
    allowed = {"square", "rectangle"} if a.shape == "all" else {a.shape}
    blocks = P.load_blocks(a.file, shapes=allowed, square_tol=0.05)
    print(f"real eligible seeds: {len(blocks)} (thickness {a.t_lo}-{a.t_hi} mm, shape {a.shape})")

    queue = P._mixed_landscape(blocks)                  # MIXED real packing (square+rect, whole plate)
    img_dir = "images_demofill"; os.makedirs(img_dir, exist_ok=True)
    for f in glob.glob(f"{img_dir}/*.png"):
        os.remove(f)
    wb = Workbook(); sm = wb.active; sm.title = "Summary"
    sm.append(["PLATE", "REAL_SEEDS", "BIG_FILLERS", "DUMMY_2x2", "PLATE_FILL_%"])
    pi = total_real = 0; fills = []
    while queue:
        real_placed = P._mixed_one_plate(queue)         # real seeds, mixed rows, whole circle
        if not real_placed:
            break
        pi += 1
        big, small = hybrid_fill(real_placed, R, min_size=a.min_seed, step=0.5)
        placed = list(real_placed)
        for k, (x, y, w, h) in enumerate(big, 1):
            placed.append({"stock": f"FILL-{pi:02d}-F{k}", "cts": 0.0, "L": w, "W": h, "H": 0.0,
                           "x": x, "y": y, "w": w, "h": h, "angle": 0, "filler": True, "kind": "big"})
        for k, (x, y) in enumerate(small, 1):
            placed.append({"stock": f"FILL-{pi:02d}-D{k}", "cts": 0.0, "L": a.min_seed, "W": a.min_seed,
                           "H": 0.0, "x": x, "y": y, "w": a.min_seed, "h": a.min_seed, "angle": 0,
                           "filler": True, "kind": "dummy"})
        real = [p for p in placed if not p.get("filler")]
        fill = 100 * sum(p["w"] * p["h"] for p in placed) / circle_area
        fills.append(fill); total_real += len(real)
        print(f"  plate {pi:02d}: {len(real)} real + {len(big)} big + {len(small)} dummy(2×2) "
              f"-> {fill:.2f}% plate-fill")
        render_circle(placed, real, pi, R, fill, f"{img_dir}/plate_{pi:02d}.png")
        ws = wb.create_sheet(f"Plate_{pi:02d}")
        ws.append(["TYPE", "STOCK_NO", "W_mm", "H_mm", "SHAPE", "CENTER_X", "CENTER_Y", "ANGLE"])
        for p in placed:
            shp = "SQUARE" if abs(p["w"] - p["h"]) <= 0.05 * max(p["w"], p["h"]) else "RECT"
            typ = "REAL" if not p.get("filler") else ("BIG_FILLER" if p.get("kind") == "big" else "DUMMY_2x2")
            ws.append([typ, p["stock"], round(p["w"], 2), round(p["h"], 2), shp,
                       round(p["x"] + p["w"] / 2, 2), round(p["y"] + p["h"] / 2, 2), p["angle"]])
        sm.append([pi, len(real), len(big), len(small), round(fill, 2)])
    if pi:
        sm.append([]); sm.append(["AVG", "", "", "", round(sum(fills) / pi, 2)])
    for c in range(1, 6):
        sm.cell(1, c).fill = PatternFill("solid", fgColor="1F4E78")
        sm.cell(1, c).font = Font(bold=True, color="FFFFFF")
    P.safe_save(wb, "arrangement_demofill.xlsx")
    print(f"-> {pi} plates, avg {sum(fills) / max(1, pi):.2f}% plate-fill  "
          f"(images_demofill\\, arrangement_demofill.xlsx)")


if __name__ == "__main__":
    main()
