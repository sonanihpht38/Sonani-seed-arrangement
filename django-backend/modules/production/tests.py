# Tests for modules.production.shapes — the irregular-seed corner validator.
#
# SimpleTestCase (not TestCase) on purpose: this module is pure geometry with no
# model access, so the suite must not need — or touch — a database.

import io

from django.test import SimpleTestCase, TransactionTestCase
from openpyxl import Workbook

from .shapes import (
    MIN_ANGLE_DEG, bounding_box, edge_lengths, fit_polygon_in_seat,
    interior_angles, parse_corners, polygon_area, validate_corners,
)

# The three worked examples from the datasheet template.
PENTAGON = "0,0; 12.4,0; 12.4,6.5; 9.2,9.8; 0,9.8"          # 12.40 x 9.80, one cut corner
HEXAGON = "0,0; 11,0; 14,3; 14,10; 3,10; 0,7"               # 14.00 x 10.00, two cut corners
SQ_CUT = "0,0; 10,0; 10,7.5; 7.5,10; 0,10"                  # 10.00 x 10.00, one cut corner


class ParseCornersTests(SimpleTestCase):
    def test_reads_a_plain_list(self):
        self.assertEqual(parse_corners("0,0; 1,0; 1,1"), [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])

    def test_tolerates_whitespace_and_newlines(self):
        self.assertEqual(parse_corners("  0,0 ;\n 1,0 ; 1,1  "),
                         [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])

    def test_drops_an_explicitly_closed_ring(self):
        # The format says don't repeat the first point, but closing it is harmless.
        self.assertEqual(parse_corners("0,0; 1,0; 1,1; 0,0"),
                         [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])

    def test_blank_is_none(self):
        for raw in (None, "", "   "):
            self.assertIsNone(parse_corners(raw))

    def test_malformed_is_none(self):
        for raw in ("0,0; 1", "0,0; a,b", "0,0; 1,2,3"):
            self.assertIsNone(parse_corners(raw), raw)


class GeometryTests(SimpleTestCase):
    def test_interior_angles_of_the_pentagon(self):
        angs = interior_angles(parse_corners(PENTAGON))
        self.assertEqual([round(a) for a in angs], [90, 90, 136, 134, 90])

    def test_angle_sum_matches_the_n_gon_identity(self):
        # Sum of interior angles of a simple n-gon is (n-2)*180. This is the test
        # that catches an inverted orientation, which yields exterior angles.
        for raw in (PENTAGON, HEXAGON, SQ_CUT):
            pts = parse_corners(raw)
            self.assertAlmostEqual(sum(interior_angles(pts)), (len(pts) - 2) * 180, places=6, msg=raw)

    def test_angles_are_orientation_independent(self):
        pts = parse_corners(PENTAGON)
        forward = sorted(round(a, 6) for a in interior_angles(pts))
        reverse = sorted(round(a, 6) for a in interior_angles(list(reversed(pts))))
        self.assertEqual(forward, reverse)

    def test_area_and_bbox(self):
        pts = parse_corners(PENTAGON)
        # 12.4 x 9.8 rectangle (121.52) minus the 3.2 x 3.3 corner triangle (5.28)
        self.assertAlmostEqual(polygon_area(pts), 116.24, places=6)
        x0, y0, bw, bh = bounding_box(pts)
        self.assertEqual((x0, y0), (0.0, 0.0))
        self.assertAlmostEqual(bw, 12.4)
        self.assertAlmostEqual(bh, 9.8)

    def test_edge_lengths_close_the_ring(self):
        self.assertEqual(len(edge_lengths(parse_corners(PENTAGON))), 5)


class ValidateAcceptsTests(SimpleTestCase):
    def test_accepts_the_three_template_shapes(self):
        for raw, L, W in ((PENTAGON, 12.40, 9.80), (HEXAGON, 14.00, 10.00), (SQ_CUT, 10.00, 10.00)):
            coords, reason = validate_corners(raw, L, W)
            self.assertIsNone(reason, "%s -> %s" % (raw, reason))
            self.assertIsNotNone(coords)

    def test_blank_is_not_an_error(self):
        # Blank means "plain rectangle" — today's behaviour, and NOT a warning.
        for raw in (None, "", "   "):
            coords, reason = validate_corners(raw, 10.0, 10.0)
            self.assertIsNone(coords)
            self.assertIsNone(reason)

    def test_result_is_reorigined_to_zero(self):
        shifted = "100,50; 112.4,50; 112.4,56.5; 109.2,59.8; 100,59.8"
        coords, reason = validate_corners(shifted, 12.40, 9.80)
        self.assertIsNone(reason)
        self.assertEqual(coords[0], (0.0, 0.0))
        self.assertEqual(coords, validate_corners(PENTAGON, 12.40, 9.80)[0])

    def test_accepts_clockwise_ordering(self):
        cw = list(reversed(parse_corners(PENTAGON)))
        raw = "; ".join("%g,%g" % p for p in cw)
        _, reason = validate_corners(raw, 12.40, 9.80)
        self.assertIsNone(reason)

    def test_bbox_tolerance_is_five_percent(self):
        # 12.4 measured, outline spans 12.4 -> a 4% error on Length still passes.
        _, reason = validate_corners(PENTAGON, 12.4 * 1.04, 9.80)
        self.assertIsNone(reason)


class ValidateRejectsTests(SimpleTestCase):
    def _reason(self, raw, L=10.0, W=10.0):
        coords, reason = validate_corners(raw, L, W)
        self.assertIsNone(coords)
        self.assertIsNotNone(reason)
        return reason

    def test_rejects_unreadable_text(self):
        self.assertIn("could not be read", self._reason("not a corner list"))

    def test_rejects_a_four_corner_shape(self):
        # All angles >= 90 on 4 corners is always a rectangle — so this is bad data.
        self.assertIn("at least 5", self._reason("0,0; 10,0; 10,10; 0,10"))

    def test_rejects_too_many_corners(self):
        pts = "; ".join("%g,%g" % (i, i % 2) for i in range(14))
        self.assertIn("more than the", self._reason(pts))

    def test_rejects_a_reflex_corner(self):
        # An L-shape: 6 corners, but one caves inward at 270 degrees.
        self.assertIn("reflex", self._reason("0,0; 10,0; 10,4; 4,4; 4,10; 0,10"))

    def test_rejects_an_acute_corner(self):
        # A 5-point arrowhead with a sharp tip.
        reason = self._reason("0,0; 10,0; 10,10; 5,3; 0,10")
        self.assertTrue("below the %.0f deg" % MIN_ANGLE_DEG in reason or "reflex" in reason, reason)

    def test_rejects_a_shape_from_the_wrong_row(self):
        # A valid pentagon, but the row says the seed is 20 x 20.
        self.assertIn("right row", self._reason(PENTAGON, 20.0, 20.0))

    def test_rejects_a_hairline_edge(self):
        self.assertIn("shortest side", self._reason("0,0; 10,0; 10,9.9; 10,10; 0,10"))

    def test_rejects_zero_area(self):
        self.assertIn("zero area", self._reason("0,0; 1,1; 2,2; 3,3; 4,4"))

    def test_rejects_missing_length_or_width(self):
        self.assertIn("cannot be checked", self._reason(PENTAGON, None, 9.8))

    def test_rejects_nonpositive_dimensions(self):
        self.assertIn("greater than zero", self._reason(PENTAGON, 0.0, 9.8))

    def test_rejects_a_self_crossing_outline(self):
        self.assertIsNotNone(self._reason("0,0; 10,0; 0,10; 10,10; 5,20", 10.0, 20.0))


def _sheet(header, rows):
    """An in-memory .xlsx, so these stay SimpleTestCase (no DB, no fixtures)."""
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


LEGACY_HDR = ["BatchNo", "StockNo", "Pcs", "Cts", "Length", "Width", "Height"]
NEW_HDR = LEGACY_HDR + ["Corners"]


class ReadRowsBackwardCompatTests(SimpleTestCase):
    """The Corners column is additive. A sheet in the ORIGINAL 7-column layout
    must parse exactly as it did before the column existed."""

    def _read(self, header, rows):
        from .services import SeedImportService
        return SeedImportService.read_rows(_sheet(header, rows))

    def test_legacy_seven_column_sheet_still_parses(self):
        rows = self._read(LEGACY_HDR, [("B1", "S-1", 1, 0.5, 10.0, 8.0, 0.70)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["batch_no"], "B1")
        self.assertEqual(rows[0]["stock_no"], "S-1")
        self.assertIsNone(rows[0]["corners_raw"])

    def test_blank_and_totals_rows_are_still_skipped(self):
        rows = self._read(LEGACY_HDR, [
            ("B1", "S-1", 1, 0.5, 10.0, 8.0, 0.70),
            (None, None, None, None, None, None, None),     # entirely empty
            (None, None, 99, 9.9, None, None, None),        # totals: no batch, no stock
        ])
        self.assertEqual([r["stock_no"] for r in rows], ["S-1"])

    def test_a_row_with_only_an_outline_is_not_a_seed(self):
        # No batch and no stock number: still skipped, exactly as before.
        rows = self._read(NEW_HDR, [(None, None, None, None, None, None, None, PENTAGON)])
        self.assertEqual(rows, [])


class ReadRowsCornersTests(SimpleTestCase):
    def _read(self, rows):
        from .services import SeedImportService
        return SeedImportService.read_rows(_sheet(NEW_HDR, rows))

    def test_outline_is_carried_through_verbatim(self):
        rows = self._read([("B1", "S-2", 1, 0.8, 12.4, 9.8, 0.70, PENTAGON)])
        self.assertEqual(rows[0]["corners_raw"], PENTAGON)

    def test_blank_corner_cell_reads_as_none(self):
        rows = self._read([
            ("B1", "S-3", 1, 0.6, 10.0, 10.0, 0.71, ""),
            ("B1", "S-4", 1, 0.6, 10.0, 10.0, 0.71, "   "),
            ("B1", "S-5", 1, 0.6, 10.0, 10.0, 0.71, None),
        ])
        self.assertEqual([r["corners_raw"] for r in rows], [None, None, None])

    def test_invalid_text_is_kept_for_the_validator_to_reject(self):
        # read_rows does no validation - it has no L/W context. It passes the text
        # on so import_seeds can reject it and emit a warning.
        rows = self._read([("B1", "S-6", 1, 0.6, 10.0, 10.0, 0.71, "rubbish")])
        self.assertEqual(rows[0]["corners_raw"], "rubbish")


class PolyFromSeedTests(SimpleTestCase):
    """engine_runner._poly_from_seed must degrade to the rectangle on any stored
    value it cannot trust, rather than break a packing run."""

    def _poly(self, stored):
        """Returns (points, assumed) — see engine_runner._poly_from_seed."""
        from .engine_runner import _poly_from_seed

        class Row:
            corners_json = stored
        return _poly_from_seed(Row())

    def test_null_and_blank_give_none(self):
        for v in (None, ""):
            self.assertEqual(self._poly(v), (None, False))

    def test_unparseable_gives_none(self):
        for v in ("not json", "{}", "[1,2,3]", '[["a","b"],["c","d"]]'):
            self.assertEqual(self._poly(v), (None, False), v)

    def test_too_few_points_gives_none(self):
        self.assertEqual(self._poly("[[0,0],[1,0]]"), (None, False))

    def test_valid_outline_round_trips(self):
        self.assertEqual(
            self._poly("[[0,0],[12.4,0],[12.4,6.5],[9.2,9.8],[0,9.8]]"),
            ([(0.0, 0.0), (12.4, 0.0), (12.4, 6.5), (9.2, 9.8), (0.0, 9.8)], False))

    def test_assumed_corner_round_trips_and_is_flagged(self):
        """A blank cross corner is stored as {"pts": ..., "assumed": true} so the
        packer can hold those stones back — a bare list must stay unflagged."""
        pts, assumed = self._poly(
            '{"pts": [[0,0],[12.4,0],[12.4,6.5],[9.2,9.8],[0,9.8]], "assumed": true}')
        self.assertEqual(pts, [(0.0, 0.0), (12.4, 0.0), (12.4, 6.5),
                               (9.2, 9.8), (0.0, 9.8)])
        self.assertTrue(assumed)

    def test_assumed_dict_without_points_gives_none(self):
        self.assertEqual(self._poly('{"assumed": true}'), (None, False))


def _rect_seed(stock, L, W, H=0.50):
    return {"stock": stock, "cts": 1.0, "L": L, "W": W, "H": H, "shape": "rectangle"}


def _cut_seed(stock, L, W, p, q, H=0.50):
    """A blank L x W with the top-right corner ground off by p (x) and q (y)."""
    s = _rect_seed(stock, L, W, H)
    s["poly"] = [(0, 0), (L, 0), (L, W - q), (L - p, W), (0, W)]
    return s


class PlateInvariantTests(SimpleTestCase):
    """Hard guarantees for every generated Max Coverage plate.

    A breach here means a WRONG PLATE, whatever coverage it claims — a seed
    overlapping its neighbour, hanging off the edge, silently shrunk, mirrored,
    or placed twice. Accuracy is the point of this module, so these are asserted
    on every seed mix rather than spot-checked.

    Pure geometry on synthetic seeds: no database, no fixtures.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import tempfile
        cls.tmp = tempfile.mkdtemp(prefix="plate-inv-")

    def _plate(self, pool, R=45.0, tag="t"):
        import os

        from .engine_runner import D
        return D.enhanced_plate_job(
            (list(pool), 1, 2 * R, R, 2.0, os.path.join(self.tmp, tag + ".png")))

    @staticmethod
    def _mix():
        pool = [_rect_seed("R%02d" % i, 11.0 + (i % 4) * 0.5, 8.6) for i in range(14)]
        pool += [_cut_seed("C%02d" % i, 9.5, 8.6, 2.0 + (i % 3) * 0.4, 1.8)
                 for i in range(6)]
        return pool

    @staticmethod
    def _saturating_mix():
        """More seeds than the plate can hold.

        _mix() is deliberately small — every stone finds a seat, which is what
        the congruence and overlap tests want. It cannot show a layout FAULT
        though: with room to spare, a broken row sweep still places everything,
        just untidily. Judging how well the plate is packed needs it full.
        """
        pool = [_rect_seed("R%02d" % i, 11.0 + (i % 4) * 0.5, 8.6) for i in range(48)]
        pool += [_cut_seed("C%02d" % i, 9.5, 8.6, 2.0 + (i % 3) * 0.4, 1.8)
                 for i in range(18)]
        return pool

    def test_no_two_seeds_overlap(self):
        from shapely.geometry import Polygon as ShPoly
        _, placed, _f, _s, _ = self._plate(self._mix(), tag="ovl")
        polys = [ShPoly(p["poly"]) for p in placed]
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                if polys[i].intersects(polys[j]):
                    self.assertLessEqual(
                        polys[i].intersection(polys[j]).area, 0.01,
                        "%s overlaps %s" % (placed[i]["stock"], placed[j]["stock"]))

    def test_every_seed_lies_inside_the_plate(self):
        from shapely.geometry import Point, Polygon as ShPoly
        R = 45.0
        _, placed, _f, _s, _ = self._plate(self._mix(), R=R, tag="in")
        disc = Point(0, 0).buffer(R, resolution=360)
        for p in placed:
            self.assertLessEqual(ShPoly(p["poly"]).difference(disc).area, 0.02,
                                 "%s hangs off the plate" % p["stock"])

    def test_no_seed_is_trimmed(self):
        # The engine must never cut a seed: seeds arrive already cut.
        from .engine_runner import D
        pool = self._mix()
        _, placed, _f, _s, _ = self._plate(pool, tag="trim")
        src = {str(s["stock"]): D._seed_footprint(s).area for s in pool}
        for p in placed:
            self.assertAlmostEqual(p["area"], src[str(p["stock"])], places=2,
                                   msg="%s was resized" % p["stock"])

    def test_rotation_only_never_mirrored(self):
        import math

        from shapely.geometry import Polygon as ShPoly

        from .engine_runner import D

        def edges(g):
            c = list(g.exterior.coords)
            return sorted(round(math.dist(c[i], c[i + 1]), 4) for i in range(len(c) - 1))

        def sign(g):
            c = list(g.exterior.coords)
            return sum(c[i][0] * c[i + 1][1] - c[i + 1][0] * c[i][1]
                       for i in range(len(c) - 1)) > 0

        pool = self._mix()
        _, placed, _f, _s, _ = self._plate(pool, tag="rot")
        src = {str(s["stock"]): D._seed_footprint(s) for s in pool}
        for p in placed:
            g0, g1 = src[str(p["stock"])], ShPoly(p["poly"])
            self.assertEqual(edges(g0), edges(g1), "%s is not congruent" % p["stock"])
            self.assertEqual(sign(g0), sign(g1), "%s was mirrored" % p["stock"])

    def test_no_seed_is_placed_twice(self):
        _, placed, _f, _s, _ = self._plate(self._mix(), tag="dup")
        stocks = [p["stock"] for p in placed]
        self.assertEqual(len(stocks), len(set(stocks)))

    def test_reported_fill_matches_the_real_union(self):
        import math

        from shapely.geometry import Polygon as ShPoly
        from shapely.ops import unary_union
        R = 45.0
        _, placed, fill, _s, _ = self._plate(self._mix(), R=R, tag="fill")
        union = unary_union([ShPoly(p["poly"]).buffer(0) for p in placed]).area
        self.assertAlmostEqual(fill, 100 * union / (math.pi * R * R), places=2)

    def test_fill_can_never_exceed_the_plate(self):
        # Summing seat areas once reported 107% by double-counting an overlap.
        _, _p, fill, _s, _ = self._plate(self._mix(), tag="cap")
        self.assertLessEqual(fill, 100.0)

    def test_no_cut_is_ever_reported(self):
        from .engine_runner import dim_rows, seed_cut
        _, placed, _f, _s, _ = self._plate(self._mix(), tag="cut")
        for p in placed:
            self.assertLessEqual(seed_cut(p)[0], 0.005, "%s reports a cut" % p["stock"])
        for r in dim_rows(placed):
            self.assertEqual(r["cut"], "—")

    def test_generation_is_deterministic(self):
        a = self._plate(self._mix(), tag="d1")
        b = self._plate(self._mix(), tag="d2")
        self.assertEqual(len(a[1]), len(b[1]))
        self.assertAlmostEqual(a[2], b[2], places=9)
        for x, y in zip(a[1], b[1]):
            self.assertEqual(x["stock"], y["stock"])
            self.assertEqual(x["poly"], y["poly"])

    def test_distance_between_seeds_is_honoured(self):
        """The criteria form's "Distance between seeds" must actually separate
        them. Max Coverage ignored it entirely — seeds were slid until they
        touched — so every plate came out edge-to-edge whatever was asked for."""
        import itertools

        from shapely.geometry import Polygon as ShPoly

        from .engine_runner import P
        before = P.CLEARANCE
        try:
            for want in (0.0, 0.5, 1.5):
                P.CLEARANCE = want
                _, placed, _f, _s, _ = self._plate(self._mix(), tag="clr%s" % want)
                polys = [ShPoly(p["poly"]) for p in placed]
                gaps = [a.distance(b) for a, b in itertools.combinations(polys, 2)]
                if not gaps:
                    continue
                self.assertGreaterEqual(
                    min(gaps), want - 0.05,
                    "asked for %.2f mm between seeds, closest pair is %.3f mm"
                    % (want, min(gaps)))
        finally:
            P.CLEARANCE = before

    def test_rows_stay_whole_at_every_clearance(self):
        """A non-zero gap must not wreck the layout — only shrink it.

        Centre-out builds each row in two halves that grow towards each other.
        Both halves once stopped at x=0, so with a gap asked for, the first
        LEFTWARD stone of every row landed flush against the first rightward one;
        free() refused it for being 0 mm away when `clear` mm were required, and
        because no orientation of any seed could ever satisfy that seat the whole
        left half of the row was marked dead. Rows degenerated into stubs and the
        leftovers were scattered by the sweep-up pass.

        test_distance_between_seeds_is_honoured did NOT catch this: the surviving
        stones were correctly spaced. The plate was simply much worse. So the
        invariant here is structural — rows must stay populated.

        Measured on this pool, stones per row: 5.0 fixed against 2.0 before, at
        every non-zero clearance. Zero is unaffected either way, which is the
        other half of the guarantee.
        """
        from .engine_runner import D, P
        pool = self._saturating_mix()
        before, seen = P.CLEARANCE, {}
        try:
            for want in (0.0, 0.25, 0.5, 1.0):
                P.CLEARANCE = want
                placed, fill = D._pack_once(
                    (list(pool), 1, 90.0, 45.0, 2.0,
                     __import__("os").path.join(self.tmp, "rw%s.png" % want)),
                    -45.0, "cut-first", "centre")
                rows = {}
                for p in placed:
                    rows.setdefault(round(p["y"], 0), []).append(p)
                per_row = len(placed) / max(1, len(rows))
                seen[want] = fill
                self.assertGreaterEqual(
                    per_row, 3.5,
                    "at %.2f mm the rows collapsed: %d seeds spread over %d rows "
                    "(%.2f per row)" % (want, len(placed), len(rows), per_row))
            # ...and a small gap must cost a little coverage, not a cliff.
            self.assertGreaterEqual(
                seen[0.25], seen[0.0] - 6.0,
                "0.25 mm between seeds dropped coverage from %.2f%% to %.2f%%"
                % (seen[0.0], seen[0.25]))
        finally:
            P.CLEARANCE = before

    def test_clearance_is_between_seeds_not_from_the_rim(self):
        # The clear ring around the plate is the MARGIN, taken out of R already.
        # Clearance must not shrink the usable circle on top of that.
        from shapely.geometry import Point, Polygon as ShPoly

        from .engine_runner import P
        R = 45.0
        before = P.CLEARANCE
        try:
            P.CLEARANCE = 1.5
            _, placed, _f, _s, _ = self._plate(self._mix(), R=R, tag="clrrim")
            disc = Point(0, 0).buffer(R, resolution=360)
            for p in placed:
                self.assertLessEqual(ShPoly(p["poly"]).difference(disc).area, 0.02)
        finally:
            P.CLEARANCE = before

    def test_empty_pool_produces_an_empty_plate(self):
        _, placed, fill, _s, _ = self._plate([], tag="empty")
        self.assertEqual(placed, [])
        self.assertEqual(fill, 0.0)

    def test_cut_seeds_are_not_stranded_inland(self):
        # A cut corner in the middle of the plate is a hole; against the rim it
        # costs nothing. No placed cut seed should waste much plate.
        from shapely.geometry import Point, Polygon as ShPoly

        from .engine_runner import D
        R = 45.0
        _, placed, _f, _s, _ = self._plate(self._mix(), R=R, tag="inland")
        disc = Point(0, 0).buffer(R, resolution=360)
        for p in placed:
            if p.get("irregular"):
                self.assertLessEqual(
                    D._wasted_area(ShPoly(p["poly"]), disc), 3.0,
                    "%s sits inland and leaves a hole" % p["stock"])

    def test_every_cut_seed_faces_outward(self):
        """MANDATORY: a ground corner always points AWAY from the plate centre.

        Turned inward it opens a wedge against a flat neighbour that no stone
        can enter, and the shop floor rejects the seat — so this is a hard rule,
        not a preference, and it has to hold for EVERY placed stone whichever
        pass seated it. The main scan tested it inline; _fill_row_ends,
        _fill_remaining_space and the row rebuilds went through _cut_on_rim,
        which did not, and two inward-facing crosses reached a real Ø90 plate.
        """
        from shapely.geometry import Polygon as ShPoly

        from .engine_runner import D
        R = 45.0
        _, placed, _f, _s, _ = self._plate(self._mix(), R=R, tag="outward")
        checked = 0
        for p in placed:
            if not p.get("irregular"):
                continue
            g = ShPoly(p["poly"])
            cut = D._cut_direction(g)
            if cut is None:
                continue
            checked += 1
            self.assertGreater(
                D._outward_score(g, cut, 0), 0.0,
                "%s has its cross facing INWARD" % p["stock"])
        self.assertGreater(checked, 0, "no cut seed was placed — test proves nothing")

    def test_the_rim_gate_refuses_an_inward_cross(self):
        """_cut_on_rim is the single gate; prove it rejects on direction alone.

        Same stone, same distance from the rim, same notch size — only the
        orientation differs. The outward one must be accepted and the inward one
        refused, or the gate is still only testing proximity.
        """
        from shapely import affinity
        from shapely.geometry import Polygon as ShPoly

        from .engine_runner import D
        R = 45.0
        # A 10 x 8 blank with the top-right corner ground off, seated hard
        # against the RIGHT rim so the cut faces out (+x).
        #
        # The cut legs are 2 mm, giving a 2.0 mm2 triangle — deliberately UNDER
        # CUT_NOTCH_MAX (3.0). A bigger cut fails the notch test on its own and
        # the assertion would pass for the wrong reason, proving nothing about
        # direction. This size is also representative: the corner triangles in
        # stock run a median 2.22 mm2, which is exactly why inward-facing crosses
        # slipped through a gate that only measured the notch.
        outward = ShPoly([(0, 0), (10, 0), (10, 6), (8, 8), (0, 8)])
        outward = affinity.translate(outward, R - 10.0, -4.0)
        self.assertTrue(D._cut_on_rim(outward, R),
                        "a cross facing outward at the rim must be allowed")

        # The SAME stone rotated 180 degrees about its own centre: still at the
        # rim, still the same notch area, cross now facing IN.
        inward = affinity.rotate(outward, 180, origin="centroid")
        self.assertFalse(D._cut_on_rim(inward, R),
                         "a cross facing inward must be refused")

        # A TANGENTIAL cross — the cut points along the rim rather than through
        # it. This is the case the reported plate actually contained (+0.060),
        # and the old `out > 0.0` rule admitted it.
        tangential = None
        for deg in range(0, 360, 5):
            cand = affinity.rotate(outward, deg, origin="centroid")
            score = D._outward_score(cand, D._cut_direction(cand), 0)
            if 0.0 < score < D.CUT_OUTWARD_MIN:
                tangential = (cand, score)
                break
        self.assertIsNotNone(tangential, "no tangential orientation found to test")
        cand, score = tangential
        self.assertFalse(
            D._cut_on_rim(cand, R),
            "a cross only %.3f outward passed the gate — 'not facing inward' is "
            "not the rule; it must face OUT by at least %.2f" % (score, D.CUT_OUTWARD_MIN))

    def test_the_rim_gate_matches_its_documented_rule_at_every_angle(self):
        """The gate must be exactly: near the rim AND facing out AND small notch.

        Property test over every orientation rather than a couple of examples —
        this is what stops the three rules drifting apart again, which is how the
        direction test came to be missing from the one place three seating paths
        rely on.
        """
        import math

        from shapely import affinity
        from shapely.geometry import Point, Polygon as ShPoly

        from .engine_runner import D
        R = 45.0
        disc = Point(0, 0).buffer(R, resolution=180)
        stone = ShPoly([(0, 0), (10, 0), (10, 6), (8, 8), (0, 8)])
        stone = affinity.translate(stone, R - 10.0, -4.0)

        for deg in range(0, 360, 10):
            g = affinity.rotate(stone, deg, origin="centroid")
            gap = R - max(math.hypot(px, py) for px, py in g.exterior.coords)
            cut = D._cut_direction(g)
            score = D._outward_score(g, cut, 0) if cut is not None else 1.0
            expected = (gap <= D.RIM_FLUSH
                        and score >= D.CUT_OUTWARD_MIN
                        and D._wasted_area(g, disc) <= D.CUT_NOTCH_MAX)
            self.assertEqual(
                D._cut_on_rim(g, R), expected,
                "at %d deg the gate disagrees with its own rule "
                "(gap %.2f, outward %.3f)" % (deg, gap, score))


class PlateMasterUnassignTests(TransactionTestCase):
    """Freeing a plate from the Plate Master screen, and deleting one safely.

    MST_SeedPlate / TRN_SeedPlate are managed=False (SQL Server DDL), so the
    test database has no such tables — every other test in this file avoids the
    database for that reason. These rules cannot be checked without one, so the
    tables are built here from the model definitions and torn down after.
    """

    reset_sequences = True

    @classmethod
    def _unmanaged(cls):
        from django.apps import apps
        return [m for m in apps.get_app_config("production").get_models()
                if not m._meta.managed]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.db import connection
        with connection.schema_editor() as se:
            for m in cls._unmanaged():
                se.create_model(m)

    @classmethod
    def tearDownClass(cls):
        from django.db import connection
        with connection.schema_editor() as se:
            for m in cls._unmanaged():
                se.delete_model(m)
        super().tearDownClass()

    def setUp(self):
        import uuid as _uuid

        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        from .models import SeedArrangePlate, SeedPlate
        SeedPlate.objects.all().delete()
        SeedArrangePlate.objects.all().delete()
        self.SeedPlate, self.SeedArrangePlate = SeedPlate, SeedArrangePlate
        self.arrange_id = _uuid.uuid4()
        self.user = get_user_model().objects.create_superuser("pm", "pm@x.y", "pw12345!")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _assigned_plate(self, name="P-USED"):
        p = self.SeedPlate.objects.create(plate_name=name, diameter=90, is_active=True,
                                          is_used=True, is_released=False)
        self.SeedArrangePlate.objects.create(arrange_id=self.arrange_id, plate_no=1,
                                             plate_id=p.plate_id, plate_name=name)
        return p

    def test_unassign_frees_the_plate_and_clears_the_arrangement(self):
        """Both sides must be cleared. Freeing only the master row would leave
        the arrangement still naming the plate, so the same physical plate could
        be handed to a second arrangement."""
        p = self._assigned_plate()
        r = self.client.post("/api/production/plate-master/%d/release/" % p.plate_id,
                             {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db()
        self.assertFalse(p.is_used)
        self.assertTrue(p.is_released)
        row = self.SeedArrangePlate.objects.get(arrange_id=self.arrange_id, plate_no=1)
        self.assertIsNone(row.plate_name)
        self.assertIsNone(row.plate_id)

    def test_unassigned_plate_returns_to_the_available_pool(self):
        p = self._assigned_plate()
        avail = self.client.get("/api/production/plates").json()
        self.assertNotIn(p.plate_name, [a["plateName"] for a in avail])
        self.client.post("/api/production/plate-master/%d/release/" % p.plate_id,
                         {}, format="json")
        avail = self.client.get("/api/production/plates").json()
        self.assertIn(p.plate_name, [a["plateName"] for a in avail])

    def test_deleting_an_assigned_plate_is_refused(self):
        """It used to succeed and take the master row with it, leaving the
        arrangement pointing at a Plate_ID that no longer existed."""
        p = self._assigned_plate()
        r = self.client.delete("/api/production/plate-master/%d/" % p.plate_id)
        self.assertEqual(r.status_code, 409, r.content)
        self.assertIn("Unassign it first", r.json()["detail"])
        self.assertTrue(self.SeedPlate.objects.filter(pk=p.plate_id).exists())
        row = self.SeedArrangePlate.objects.get(arrange_id=self.arrange_id, plate_no=1)
        self.assertEqual(row.plate_name, p.plate_name)

    def test_unassign_then_delete_succeeds(self):
        # The route out of the refusal above — and the reason blocking is safe.
        p = self._assigned_plate()
        self.client.post("/api/production/plate-master/%d/release/" % p.plate_id,
                         {}, format="json")
        r = self.client.delete("/api/production/plate-master/%d/" % p.plate_id)
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(self.SeedPlate.objects.filter(pk=p.plate_id).exists())

    def test_deleting_a_free_plate_still_works(self):
        # Unchanged behaviour: only ASSIGNED plates are protected.
        p = self.SeedPlate.objects.create(plate_name="P-FREE", diameter=90, is_active=True)
        r = self.client.delete("/api/production/plate-master/%d/" % p.plate_id)
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(self.SeedPlate.objects.filter(pk=p.plate_id).exists())

    def test_a_released_plate_can_be_deleted(self):
        p = self.SeedPlate.objects.create(plate_name="P-REL", diameter=90, is_active=True,
                                          is_used=True, is_released=True)
        self.assertEqual(
            self.client.delete("/api/production/plate-master/%d/" % p.plate_id).status_code, 204)

    def test_unassign_rejects_an_unknown_plate(self):
        r = self.client.post("/api/production/plate-master/999999/release/", {}, format="json")
        self.assertIn(r.status_code, (400, 404), r.content)

    def test_finalization_release_is_unchanged(self):
        """The arrangement-keyed release that Finalization uses must behave
        exactly as before — this change only ADDED a second way in."""
        p = self._assigned_plate("P-FIN")
        r = self.client.post("/api/production/plates/release",
                             {"arrangeId": str(self.arrange_id), "plateNo": 1}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        # `seedsReturned` was added when releasing started giving a plate's
        # seeds back; the release behaviour itself is unchanged.
        self.assertEqual(r.json()["released"], True)
        self.assertEqual(r.json()["plateName"], "P-FIN")
        p.refresh_from_db()
        self.assertFalse(p.is_used)
        self.assertTrue(p.is_released)

    def test_assign_is_unchanged(self):
        p = self.SeedPlate.objects.create(plate_name="P-NEW", diameter=90, is_active=True)
        self.SeedArrangePlate.objects.create(arrange_id=self.arrange_id, plate_no=2)
        r = self.client.post("/api/production/plates/assign",
                             {"arrangeId": str(self.arrange_id), "plateNo": 2,
                              "plateName": "P-NEW"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db()
        self.assertTrue(p.is_used)
        self.assertFalse(p.is_released)


class FinalizeConsumesSeedsTests(TransactionTestCase):
    """Finalizing an arrangement takes its seeds out of circulation.

    The point of the feature: a stone glued to a finalized plate must never be
    offered to the next run. TRN_SeedData.ISUsed / Used_ID have existed since
    the schema was written and were never populated — an earlier attempt wrote
    ISUsed at GENERATION time, consuming inventory just for previewing, and was
    rolled back. These tests pin the safe version: consumption happens only on
    an explicit finalize, and is reversible.
    """

    reset_sequences = True

    @classmethod
    def _unmanaged(cls):
        from django.apps import apps
        return [m for m in apps.get_app_config("production").get_models()
                if not m._meta.managed]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.db import connection
        with connection.schema_editor() as se:
            for m in cls._unmanaged():
                se.create_model(m)

    @classmethod
    def tearDownClass(cls):
        from django.db import connection
        with connection.schema_editor() as se:
            for m in cls._unmanaged():
                se.delete_model(m)
        super().tearDownClass()

    def setUp(self):
        import uuid as _uuid

        from .models import (
            SeedArrange, SeedArrangeDetail, SeedArrangePlate, SeedData, SeedPlate,
        )
        for m in (SeedData, SeedArrange, SeedArrangeDetail, SeedArrangePlate, SeedPlate):
            m.objects.all().delete()
        self.SeedData, self.SeedArrange = SeedData, SeedArrange
        self.SeedArrangeDetail, self.SeedArrangePlate = SeedArrangeDetail, SeedArrangePlate
        self.uuid = _uuid
        # 10 seeds; an arrangement that placed the first 6 across two plates —
        # 3 on each — leaving 4 that were never placed at all.
        self.seeds = [SeedData.objects.create(seed_id=_uuid.uuid4(), stock_no="S%02d" % i,
                                              length=11, width=9, height=0.5)
                      for i in range(10)]
        self.arrange_id = _uuid.uuid4()
        SeedArrange.objects.create(arrange_id=self.arrange_id, is_active=True, plate_no=2)
        for pno in (1, 2):
            SeedArrangePlate.objects.create(arrange_id=self.arrange_id, plate_no=pno)
        for i, s in enumerate(self.seeds[:6]):
            SeedArrangeDetail.objects.create(
                detail_id=_uuid.uuid4(), arrange_id=self.arrange_id, seed_type=False,
                seed_id=s.seed_id, plate_id=1 + (i // 3), method="enhanced")

    def _svc(self):
        from .services import InventoryService
        return InventoryService

    @staticmethod
    def _load():
        """What the packer would actually receive. _blocks_from_seeds gates on
        the P.T_LO/P.T_HI thickness globals, so they must be set first or every
        seed is filtered out regardless of ISUsed."""
        from .engine_runner import _apply_globals, load_blocks_from_db
        _apply_globals({"plateD": 90, "margin": 5.0, "tLo": 0.45, "tHi": 0.65,
                        "grid": 0.5, "clearance": 0.0, "minSeed": 2.0})
        return load_blocks_from_db({"square", "rectangle"}, 0.05)

    def _assign(self, plate_no, name):
        from .services import PlateService
        return PlateService.assign(self.arrange_id, plate_no, name, user_id=7)

    def _release(self, plate_no):
        from .services import PlateService
        return PlateService.release(self.arrange_id, plate_no, user_id=7)

    def test_assigning_one_plate_consumes_only_that_plate(self):
        """The whole point of per-plate: plate 2's stones stay available so the
        rest of the run can still be re-generated."""
        res = self._assign(1, "P-1")
        self.assertEqual(res["seedsConsumed"], 3)
        self.assertEqual(self.SeedData.objects.filter(is_used=True).count(), 3)
        for s in self.seeds[:3]:                      # plate 1
            s.refresh_from_db()
            self.assertTrue(s.is_used)
            self.assertEqual(s.used_id, self.arrange_id)
        for s in self.seeds[3:]:                      # plate 2 + never placed
            s.refresh_from_db()
            self.assertNotEqual(s.is_used, True,
                                "%s was consumed but its plate is unassigned" % s.stock_no)

    def test_unassigned_plates_stay_available_to_the_packer(self):
        self.assertEqual(len(self._load()), 10)
        self._assign(1, "P-1")
        after = self._load()
        self.assertEqual(len(after), 7)
        self.assertEqual({b["stock"] for b in after},
                         {s.stock_no for s in self.seeds[3:]})
        # ...and the second plate takes only its own three.
        self._assign(2, "P-2")
        self.assertEqual(len(self._load()), 4)

    def test_releasing_a_plate_returns_only_its_seeds(self):
        self._assign(1, "P-1")
        self._assign(2, "P-2")
        self.assertEqual(self.SeedData.objects.filter(is_used=True).count(), 6)
        res = self._release(1)
        self.assertEqual(res["seedsReturned"], 3)
        self.assertEqual(self.SeedData.objects.filter(is_used=True).count(), 3)
        for s in self.seeds[3:6]:
            s.refresh_from_db()
            self.assertTrue(s.is_used, "%s is on plate 2, still assigned" % s.stock_no)
        self.assertEqual(len(self._load()), 7)

    def test_newly_imported_seeds_join_the_available_pool(self):
        """New inventory arrives with ISUsed NULL, so it is picked up with no
        extra step — alongside whatever is left of the old stock."""
        self._assign(1, "P-1")
        self.assertEqual(len(self._load()), 7)
        for i in range(5):
            self.SeedData.objects.create(seed_id=self.uuid.uuid4(), stock_no="NEW%02d" % i,
                                         length=11, width=9, height=0.5)
        stocks = {b["stock"] for b in self._load()}
        self.assertEqual(len(stocks), 12)
        self.assertTrue({"NEW00", "NEW04"} <= stocks)
        self.assertNotIn("S00", stocks, "a consumed seed came back")

    def test_max_coverage_is_the_layout_that_counts(self):
        """Arrange and Max Coverage put 36-67% of stones on different plates, so
        the plate's seed list must come from the layout actually built."""
        # Same seeds, but the arrange layout puts them all on plate 1.
        for s in self.seeds[3:6]:
            self.SeedArrangeDetail.objects.create(
                detail_id=self.uuid.uuid4(), arrange_id=self.arrange_id, seed_type=False,
                seed_id=s.seed_id, plate_id=1, method="arrange")
        self.assertEqual(len(self._svc().seed_ids_for(self.arrange_id, 1)), 3)
        self.assertEqual(self._assign(1, "P-1")["seedsConsumed"], 3)

    def test_an_arrange_only_run_still_consumes(self):
        """No Max Coverage layout exists for older runs — falling back keeps
        them working instead of silently consuming nothing."""
        other = self.uuid.uuid4()
        self.SeedArrange.objects.create(arrange_id=other, is_active=True, plate_no=1)
        self.SeedArrangePlate.objects.create(arrange_id=other, plate_no=1)
        for s in self.seeds[6:9]:
            self.SeedArrangeDetail.objects.create(
                detail_id=self.uuid.uuid4(), arrange_id=other, seed_type=False,
                seed_id=s.seed_id, plate_id=1, method="arrange")
        self.assertEqual(len(self._svc().seed_ids_for(other, 1)), 3)

    def test_a_seed_cannot_be_claimed_by_two_plates(self):
        """A stale run generated before the first assign still lists the same
        seeds. Assigning it must fail loudly, not steal them."""
        from modules.core.exceptions import ConflictError
        from .services import PlateService
        stale = self.uuid.uuid4()
        self.SeedArrange.objects.create(arrange_id=stale, is_active=True, plate_no=1)
        self.SeedArrangePlate.objects.create(arrange_id=stale, plate_no=1)
        for s in self.seeds[:3]:
            self.SeedArrangeDetail.objects.create(
                detail_id=self.uuid.uuid4(), arrange_id=stale, seed_type=False,
                seed_id=s.seed_id, plate_id=1, method="enhanced")
        self._assign(1, "P-1")
        with self.assertRaises(ConflictError):
            PlateService.assign(stale, 1, "P-2", user_id=7)
        # ...and nothing was taken from the first plate, nor was the name set.
        for s in self.seeds[:3]:
            s.refresh_from_db()
            self.assertEqual(s.used_id, self.arrange_id)
        self.assertIsNone(
            self.SeedArrangePlate.objects.get(arrange_id=stale, plate_no=1).plate_name)

    def test_a_stale_plate_is_flagged_before_the_user_clicks(self):
        """Generate two runs from overlapping stock, assign the second's plate,
        and the first's plate must report itself unbuildable — the UI disables
        Assign on it instead of letting the click fail with a conflict."""
        from .services import PlateService
        other = self.uuid.uuid4()
        self.SeedArrange.objects.create(arrange_id=other, is_active=True, plate_no=1)
        self.SeedArrangePlate.objects.create(arrange_id=other, plate_no=1)
        for s in self.seeds[:2]:            # 2 of plate 1's 3 seeds
            self.SeedArrangeDetail.objects.create(
                detail_id=self.uuid.uuid4(), arrange_id=other, seed_type=False,
                seed_id=s.seed_id, plate_id=1, method="enhanced")
        PlateService.assign(other, 1, "P-OTHER", user_id=7)

        st = self._svc().status(self.arrange_id)
        p1 = next(p for p in st["plates"] if p["plateNo"] == 1)
        p2 = next(p for p in st["plates"] if p["plateNo"] == 2)
        self.assertFalse(p1["canAssign"], "plate 1 lost seeds and must be flagged")
        self.assertEqual(p1["takenElsewhere"], 2)
        self.assertTrue(p2["canAssign"], "plate 2 is untouched and still buildable")
        self.assertEqual(p2["takenElsewhere"], 0)

    def test_a_regenerated_run_never_sees_consumed_seeds(self):
        """The other half of the guarantee: once a plate is assigned, a fresh
        generation is built only from what is left, so it can never collide."""
        self._assign(1, "P-1")
        fresh = {b["stock"] for b in self._load()}
        self.assertEqual(len(fresh), 7)
        self.assertTrue(fresh.isdisjoint({s.stock_no for s in self.seeds[:3]}))

    def test_the_finalized_plate_list_tracks_assignment(self):
        """The register in the Finalization screen. Reads TRN_SeedPlate, so it
        must appear on assign and disappear on release — and it must not depend
        on the in-memory job, which is gone after a backend restart."""
        from .services import PlateService
        self.assertEqual(PlateService.finalized_list(), [])

        self._assign(1, "P-1")
        rows = PlateService.finalized_list()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["plateName"], "P-1")
        self.assertEqual(rows[0]["plateNo"], 1)
        self.assertEqual(rows[0]["seeds"], 3, "counts the built layout's seeds")
        self.assertEqual(rows[0]["arrangeId"], str(self.arrange_id))

        self._assign(2, "P-2")
        self.assertEqual({r["plateName"] for r in PlateService.finalized_list()},
                         {"P-1", "P-2"})

        self._release(1)
        self.assertEqual([r["plateName"] for r in PlateService.finalized_list()], ["P-2"])

    def test_the_finalized_list_endpoint_is_reachable(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=get_user_model().objects.create_superuser(
            "fl", "fl@x.y", "pw12345!"))
        self._assign(1, "P-1")
        r = c.get("/api/production/plates/finalized")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([x["plateName"] for x in r.json()], ["P-1"])

    def test_dummy_seeds_are_not_inventory(self):
        # Filler seeds carry SeedType=True and live in TRN_DummySeedData.
        self.SeedArrangeDetail.objects.create(
            detail_id=self.uuid.uuid4(), arrange_id=self.arrange_id, seed_type=True,
            seed_id=self.uuid.uuid4(), plate_id=1, method="enhanced")
        self.assertEqual(len(self._svc().seed_ids_for(self.arrange_id)), 6)

    def test_status_reports_each_plate(self):
        st = self._svc().status(self.arrange_id)
        self.assertFalse(st["isFinalized"])
        self.assertEqual(st["seedsAvailable"], 10)
        self.assertEqual([(p["plateNo"], p["seeds"], p["consumed"]) for p in st["plates"]],
                         [(1, 3, False), (2, 3, False)])
        self._assign(1, "P-1")
        st = self._svc().status(self.arrange_id)
        self.assertFalse(st["isFinalized"], "only one of two plates is named")
        self.assertEqual(st["seedsAvailable"], 7)
        self.assertEqual([(p["plateNo"], p["consumed"]) for p in st["plates"]],
                         [(1, True), (2, False)])
        self._assign(2, "P-2")
        self.assertTrue(self._svc().status(self.arrange_id)["isFinalized"])

    def test_details_pointing_at_deleted_seeds_do_not_break_assign(self):
        """Re-imports mint new Seed_IDs, so old details reference rows that are
        gone — live already has 815 distinct detail Seed_IDs against 95 seeds."""
        self.SeedArrangeDetail.objects.create(
            detail_id=self.uuid.uuid4(), arrange_id=self.arrange_id, seed_type=False,
            seed_id=self.uuid.uuid4(), plate_id=1, method="enhanced")
        self.assertEqual(self._assign(1, "P-1")["seedsConsumed"], 3)

    def test_the_http_endpoints_work_end_to_end(self):
        """The service tests bypass routing, permissions and JSON. These drive
        the real URLs the browser calls."""
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=get_user_model().objects.create_superuser(
            "fin", "fin@x.y", "pw12345!"))
        url = "/api/production/arrangements/%s/finalize" % self.arrange_id
        self.assertEqual(c.get(url).json()["seedsAvailable"], 10)

        r = c.post("/api/production/plates/assign",
                   {"arrangeId": str(self.arrange_id), "plateNo": 1, "plateName": "P-1"},
                   format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["seedsConsumed"], 3)
        self.assertEqual(c.get(url).json()["seedsAvailable"], 7)

        r = c.post("/api/production/plates/release",
                   {"arrangeId": str(self.arrange_id), "plateNo": 1}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["seedsReturned"], 3)
        self.assertEqual(c.get(url).json()["seedsAvailable"], 10)

    def test_return_all_recovers_a_bulk_consume(self):
        """The way back from seeds consumed by the earlier arrangement-level
        version, which took every plate at once."""
        self._assign(1, "P-1")
        self._assign(2, "P-2")
        self.assertEqual(self.SeedData.objects.filter(is_used=True).count(), 6)
        self.assertEqual(self._svc().unfinalize(self.arrange_id)["returned"], 6)
        self.assertEqual(len(self._load()), 10)

    def test_the_finalize_route_does_not_shadow_arrangement_detail(self):
        """`/arrangements/<id>` and `/arrangements/<id>/finalize` share a prefix;
        the order they are declared in decides whether both resolve."""
        from django.urls import resolve
        self.assertEqual(
            resolve("/api/production/arrangements/%s/finalize" % self.arrange_id).url_name,
            "finalize-arrangement")
        self.assertEqual(
            resolve("/api/production/arrangements/%s" % self.arrange_id).url_name,
            "arrangement-detail")

    def test_nothing_is_consumed_by_generating(self):
        """Generating must stay free of side effects — the reason the earlier
        attempt was rolled back."""
        self._load()
        self.assertEqual(self.SeedData.objects.filter(is_used=True).count(), 0)
        self.assertEqual(self.SeedData.objects.filter(used_id__isnull=False).count(), 0)


class DomainErrorWiringTests(SimpleTestCase):
    """The production module must raise the CANONICAL DomainError.

    config.settings wires DRF's EXCEPTION_HANDLER to
    modules.core.exceptions.domain_exception_handler, which matches on
    isinstance(exc, core DomainError). production/models.py used to define a
    private copy, so any error not caught by an explicit per-view try/except
    escaped that check and surfaced as HTTP 500 instead of a clean 400.
    """

    def test_production_domainerror_is_the_core_one(self):
        from modules.core.exceptions import DomainError as Core

        from .models import DomainError as Prod
        self.assertIs(Prod, Core)

    def test_handler_recognises_a_production_domainerror(self):
        from modules.core.exceptions import domain_exception_handler

        from .models import DomainError
        resp = domain_exception_handler(DomainError("nope"), {})
        self.assertIsNotNone(resp, "handler did not recognise the error")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"detail": "nope"})


class UuidGuardTests(SimpleTestCase):
    """A malformed arrange id must become a DomainError, not a 500.

    The arrange/plate tables key on `uniqueidentifier`; handing the ORM a
    non-UUID string makes Django's field raise ValidationError, which no view
    catches. These are pure-string checks, so no database is touched.
    """

    def _err(self, value):
        from .models import DomainError
        from .services import _uuid_or_error
        with self.assertRaises(DomainError) as cm:
            _uuid_or_error(value)
        return str(cm.exception)

    def test_rejects_malformed_ids(self):
        for v in ("does-not-exist", "", "123", "'; DROP TABLE x--", "x" * 60, None):
            self.assertIn("not a valid id", self._err(v), repr(v))

    def test_accepts_a_well_formed_uuid(self):
        import uuid as _uuid

        from .services import _uuid_or_error
        u = _uuid.uuid4()
        self.assertEqual(_uuid_or_error(str(u)), u)

    def test_field_name_appears_in_the_message(self):
        from .services import _uuid_or_error
        from .models import DomainError
        with self.assertRaises(DomainError) as cm:
            _uuid_or_error("bad", field="plateId")
        self.assertIn("plateId", str(cm.exception))


class FitPolygonInSeatTests(SimpleTestCase):
    """Max Coverage placement: a measured outline must be provably inside its seat."""

    @staticmethod
    def _box(x0, y0, x1, y1):
        from shapely.geometry import box
        return box(x0, y0, x1, y1)

    def test_fits_a_seat_that_is_comfortably_larger(self):
        stone = parse_corners(PENTAGON)                     # 12.4 x 9.8
        placed = fit_polygon_in_seat(stone, self._box(0, 0, 20, 20))
        self.assertIsNotNone(placed)

    def test_placed_outline_is_really_inside_the_seat(self):
        from shapely.geometry import Polygon as ShPoly
        seat = self._box(0, 0, 20, 20)
        placed = fit_polygon_in_seat(parse_corners(PENTAGON), seat)
        self.assertTrue(seat.buffer(1e-6).contains(ShPoly(placed)))

    def test_area_is_preserved_by_placement(self):
        stone = parse_corners(PENTAGON)
        placed = fit_polygon_in_seat(stone, self._box(0, 0, 20, 20))
        self.assertAlmostEqual(polygon_area(placed[:-1]), polygon_area(stone), places=6)

    def test_rejects_a_seat_smaller_in_area(self):
        self.assertIsNone(fit_polygon_in_seat(parse_corners(PENTAGON), self._box(0, 0, 5, 5)))

    def test_rejects_a_seat_that_is_too_narrow(self):
        # Same area as the stone, but only 2 mm wide — no rotation can fit it.
        self.assertIsNone(fit_polygon_in_seat(parse_corners(PENTAGON), self._box(0, 0, 2, 200)))

    def test_rotation_is_used_when_upright_will_not_fit(self):
        # 12.4 x 9.8 stone into a 10.5 x 13 seat: only the 90-degree turn works.
        placed = fit_polygon_in_seat(parse_corners(PENTAGON), self._box(0, 0, 10.5, 13))
        self.assertIsNotNone(placed)

    def test_empty_and_missing_inputs_are_safe(self):
        self.assertIsNone(fit_polygon_in_seat([], self._box(0, 0, 10, 10)))
        self.assertIsNone(fit_polygon_in_seat(parse_corners(PENTAGON), None))


# ============================================================================
# Seed-width band, the unplaceable-seed gate, and centre-out row ordering.
#
# SimpleTestCase throughout: each of these is a pure function over plain dicts
# or stub rows, so none of it needs a database.
# ============================================================================

class _SeedRow:
    """Stand-in for a TRN_SeedData row, carrying only the fields the loader reads."""

    def __init__(self, stock_no, length, width, height, corners_json=None, cts=1.0):
        self.stock_no = stock_no
        self.length = length
        self.width = width
        self.height = height
        self.corners_json = corners_json
        self.cts = cts


class SeedWidthTests(SimpleTestCase):
    """`seed_width` is the SHORT side, so the filter is rotation-invariant."""

    def test_width_is_the_short_side(self):
        from .engine_runner import seed_width

        self.assertEqual(seed_width(15.0, 10.0), 10.0)
        self.assertEqual(seed_width(10.0, 15.0), 10.0)

    def test_the_same_stone_measured_either_way_agrees(self):
        """The reason for not using the stored Width column: a stone entered as
        15 x 10 and its twin entered 10 x 15 must qualify or fail together."""
        from .engine_runner import seed_width

        self.assertEqual(seed_width(15.0, 10.0), seed_width(10.0, 15.0))


class FitsThePlateTests(SimpleTestCase):
    """A seed fits at all only if its DIAGONAL clears the usable diameter."""

    def test_a_normal_seed_fits(self):
        from .engine_runner import _fits_the_plate

        self.assertTrue(_fits_the_plate(12.0, 9.0, 40.0))

    def test_the_live_corrupt_row_is_rejected(self):
        """Stock DOMI002328 is stored 1285.0 x 9.03 mm on the live inventory."""
        from .engine_runner import _fits_the_plate

        self.assertFalse(_fits_the_plate(1285.0, 9.03, 40.0))

    def test_a_seed_on_the_diagonal_limit_is_accepted(self):
        """A square whose diagonal is exactly the usable diameter still fits."""
        import math

        from .engine_runner import _fits_the_plate

        side = 40.0 * math.sqrt(2) / 1.0000001   # diagonal a hair under 2R
        self.assertTrue(_fits_the_plate(side, side, 40.0))
        self.assertFalse(_fits_the_plate(side * 1.01, side, 40.0))


class WidthBandFilterTests(SimpleTestCase):
    """`_blocks_from_seeds` honours the optional band at either end."""

    ROWS = [
        _SeedRow("NARROW", 20.0, 6.0, 0.70),      # width 6
        _SeedRow("MID", 14.0, 10.0, 0.70),        # width 10
        _SeedRow("WIDE", 18.0, 16.0, 0.70),       # width 16
    ]

    def _load(self, **kw):
        from . import engine_runner as ER

        ER.P.T_LO, ER.P.T_HI, ER.P.R = 0.67, 0.73, 40.0
        blocks = ER._blocks_from_seeds(self.ROWS, {"square", "rectangle"}, 0.05, **kw)
        return sorted(b["stock"] for b in blocks)

    def test_no_band_keeps_everything(self):
        """Both ends unset must reproduce the pre-feature behaviour exactly."""
        self.assertEqual(self._load(), ["MID", "NARROW", "WIDE"])

    def test_maximum_only(self):
        self.assertEqual(self._load(w_hi=12.0), ["MID", "NARROW"])

    def test_minimum_only(self):
        self.assertEqual(self._load(w_lo=8.0), ["MID", "WIDE"])

    def test_both_ends(self):
        self.assertEqual(self._load(w_lo=8.0, w_hi=12.0), ["MID"])

    def test_bounds_are_inclusive(self):
        self.assertEqual(self._load(w_lo=10.0, w_hi=10.0), ["MID"])

    def test_an_impossible_band_matches_nothing(self):
        self.assertEqual(self._load(w_lo=30.0), [])

    def test_the_band_reads_the_short_side_not_the_stored_column(self):
        """NARROW is stored 20.0 x 6.0. A band of 4-8 must keep it (width 6);
        a band of 18-22 must not, because its long side is irrelevant."""
        self.assertIn("NARROW", self._load(w_lo=4.0, w_hi=8.0))
        self.assertNotIn("NARROW", self._load(w_lo=18.0, w_hi=22.0))


class SquareToleranceTests(SimpleTestCase):
    """`squareTol` decides where "square" ends and "rectangle" begins.

    It was hardcoded to 0 in the criteria form, which means a seed had to be
    EXACTLY square. Nothing measured to two decimals ever is, so Shape = Square
    matched nothing at all and Shape = Rectangle quietly matched everything —
    making it identical to Shape = All.
    """

    ROWS = [
        _SeedRow("NEAR-SQ", 11.89, 11.35, 0.70),   # 4.5% apart — square at 0.05
        _SeedRow("EXACT-SQ", 10.00, 10.00, 0.70),  # square at any tolerance
        _SeedRow("OBLONG", 14.35, 10.35, 0.70),    # 28% apart — never square
    ]

    def _load(self, shape, tol):
        from . import engine_runner as ER

        ER.P.T_LO, ER.P.T_HI, ER.P.R = 0.67, 0.73, 40.0
        blocks = ER._blocks_from_seeds(self.ROWS, ER.SHAPE_SETS[shape], tol)
        return sorted(b["stock"] for b in blocks)

    def test_zero_tolerance_makes_square_useless(self):
        """The reported defect: only an exactly-square seed qualifies."""
        self.assertEqual(self._load("square", 0.0), ["EXACT-SQ"])

    def test_zero_tolerance_makes_rectangle_match_everything_else(self):
        """...and Rectangle then sweeps up the near-squares too."""
        self.assertEqual(self._load("rectangle", 0.0), ["NEAR-SQ", "OBLONG"])

    def test_five_percent_classifies_a_near_square_as_square(self):
        self.assertEqual(self._load("square", 0.05), ["EXACT-SQ", "NEAR-SQ"])
        self.assertEqual(self._load("rectangle", 0.05), ["OBLONG"])

    def test_the_two_classes_always_partition_the_pool(self):
        """Every seed lands in exactly one class, whatever the tolerance — so
        no seed can be lost or counted twice by changing it."""
        for tol in (0.0, 0.02, 0.05, 0.10, 0.5):
            sq = set(self._load("square", tol))
            rect = set(self._load("rectangle", tol))
            self.assertEqual(sq | rect, {"NEAR-SQ", "EXACT-SQ", "OBLONG"}, tol)
            self.assertEqual(sq & rect, set(), tol)

    def test_shape_all_is_UNAFFECTED_by_the_tolerance(self):
        """THE GUARANTEE. Shape = All accepts both classes, so the threshold
        cannot change which seeds are arranged — every plate ever generated with
        Shape = All is identical whatever this value is set to. This is what
        makes fixing the default safe for existing output."""
        base = self._load("all", 0.0)
        self.assertEqual(base, ["EXACT-SQ", "NEAR-SQ", "OBLONG"])
        for tol in (0.02, 0.05, 0.10, 0.5, 1.0):
            self.assertEqual(self._load("all", tol), base,
                             "shape=all changed at squareTol %s" % tol)


class OversizeGateTests(SimpleTestCase):
    """One unplaceable row must not cost the run every seed behind it."""

    def _pool(self):
        return [
            _SeedRow("GOOD-1", 12.0, 9.0, 0.70),
            _SeedRow("BAD", 1285.0, 9.03, 0.70),   # the live corrupt row
            _SeedRow("GOOD-2", 11.0, 9.0, 0.70),
            _SeedRow("GOOD-3", 10.0, 8.0, 0.70),
        ]

    def test_the_oversized_row_is_excluded_and_reported(self):
        from . import engine_runner as ER

        ER.P.T_LO, ER.P.T_HI, ER.P.R = 0.67, 0.73, 40.0
        dropped = []
        blocks = ER._blocks_from_seeds(self._pool(), {"square", "rectangle"}, 0.05,
                                       oversize=dropped)
        self.assertEqual(dropped, ["BAD"])
        self.assertEqual(sorted(b["stock"] for b in blocks),
                         ["GOOD-1", "GOOD-2", "GOOD-3"])

    def test_every_good_seed_still_reaches_a_plate(self):
        """Regression. Unfiltered, BAD reaches the head of the queue, no row can
        take it, `_mixed_one_plate` returns None, and the caller's `while queue`
        loop breaks — silently dropping GOOD-2 and GOOD-3 from the arrangement.
        On the live inventory that one row stranded 190 of 634 seeds."""
        from . import engine_runner as ER
        from .engine import pack_v2 as P

        ER.P.T_LO, ER.P.T_HI, ER.P.R = 0.67, 0.73, 40.0
        P.R = 40.0
        blocks = ER._blocks_from_seeds(self._pool(), {"square", "rectangle"}, 0.05)

        queue = P._mixed_landscape(blocks)
        placed = []
        while queue:
            plate = P._mixed_one_plate(queue)
            if not plate:
                break
            placed.extend(plate)
        self.assertEqual(sorted(p["stock"] for p in placed),
                         ["GOOD-1", "GOOD-2", "GOOD-3"])


class CentreOutRowTests(SimpleTestCase):
    """Biggest seeds toward the middle of a row, smallest at the two ends."""

    def _row(self, *widths):
        return [{"stock": "S%d" % i, "w": w, "h": 9.0} for i, w in enumerate(widths)]

    def test_the_widest_seed_lands_in_the_middle(self):
        from .engine.pack_v2 import _centre_out_row

        widths = [b["w"] for b in _centre_out_row(self._row(4, 13, 6, 12, 5))]
        self.assertEqual(widths.index(max(widths)), len(widths) // 2)

    def test_widths_taper_outward_from_the_centre(self):
        from .engine.pack_v2 import _centre_out_row

        widths = [b["w"] for b in _centre_out_row(self._row(4, 13, 6, 12, 5, 11))]
        mid = len(widths) // 2
        self.assertEqual(widths[:mid], sorted(widths[:mid]))                 # rises to the middle
        self.assertEqual(widths[mid:], sorted(widths[mid:], reverse=True))   # falls away after

    def test_the_row_keeps_exactly_its_own_seeds(self):
        """A reorder, never a filter — the row's contents and total width are
        what the chord check upstream was computed against."""
        from .engine.pack_v2 import _centre_out_row

        row = self._row(4, 13, 6, 12, 5)
        out = _centre_out_row(row)
        self.assertEqual(len(out), len(row))
        self.assertEqual(sorted(b["stock"] for b in out), sorted(b["stock"] for b in row))
        self.assertAlmostEqual(sum(b["w"] for b in out), sum(b["w"] for b in row))

    def test_ordering_is_deterministic(self):
        """generate_final re-packs a saved run to redraw it, so two packs of the
        same seeds must lay out identically whatever order they arrive in."""
        from .engine.pack_v2 import _centre_out_row

        row = self._row(9, 9, 9, 12, 12)
        first = [b["w"] for b in _centre_out_row(row)]
        second = [b["w"] for b in _centre_out_row(list(reversed(row)))]
        self.assertEqual(first, second)

    def test_a_single_seed_row_is_unchanged(self):
        from .engine.pack_v2 import _centre_out_row

        self.assertEqual(_centre_out_row(self._row(7)), self._row(7))


class RimPocketFillTests(SimpleTestCase):
    """The rim-pocket pass may only ADD, and only against a neighbour.

    It is the pass that reclaims the crescent between the outermost stones and
    the plate edge. The rule that separates it from the residual fill that was
    turned off is attachment: a stone floating in open space is what made that
    one produce unbuildable plates.
    """

    def _plate(self, pool, R=45.0, tag="rim"):
        import os
        import tempfile

        from .engine_runner import D
        tmp = tempfile.mkdtemp(prefix="rim-")
        return D.enhanced_plate_job(
            (list(pool), 1, 2 * R, R, 2.0, os.path.join(tmp, tag + ".png")))

    def _mix(self):
        pool = [_rect_seed(f"R{i}", 11.0 + (i % 3) * 0.05, 9.0 + (i % 3) * 0.05)
                for i in range(24)]
        pool += [_rect_seed(f"S{i}", 3.0 + (i % 4) * 0.5, 2.6 + (i % 4) * 0.4)
                 for i in range(24)]
        pool += [_cut_seed(f"C{i}", 10.0, 8.0, 2.0, 2.0) for i in range(4)]
        return pool

    def test_added_stones_touch_the_arrangement(self):
        """Every rim-pocket stone must land against something already placed."""
        from shapely.geometry import Polygon as ShPoly

        _, placed, _f, _s, _ = self._plate(self._mix(), tag="touch")
        gs = [ShPoly(p["poly"]).buffer(0) for p in placed]
        for i, g in enumerate(gs):
            near = min((g.distance(h) for j, h in enumerate(gs) if j != i), default=0.0)
            self.assertLessEqual(
                near, 0.6,
                "%s is floating %.2f mm from anything" % (placed[i]["stock"], near))

    def test_the_pass_only_adds(self):
        """Turning it off must leave a strict SUBSET of the same plate — no seed
        moved or resized, only fewer of them."""
        from .engine_runner import D

        pool = self._mix()
        try:
            D.RIM_POCKET_FILL = False
            _, without, f_off, _s, _ = self._plate(pool, tag="off")
            D.RIM_POCKET_FILL = True
            _, with_, f_on, _s, _ = self._plate(pool, tag="on")
        finally:
            D.RIM_POCKET_FILL = True

        self.assertGreaterEqual(len(with_), len(without))
        self.assertGreaterEqual(f_on + 1e-9, f_off)
        # Every seed of the smaller plate survives unchanged in the larger one.
        seats = {(p["stock"], round(p["x"], 3), round(p["y"], 3),
                  round(p["w"], 3), round(p["h"], 3)) for p in with_}
        for p in without:
            self.assertIn(
                (p["stock"], round(p["x"], 3), round(p["y"], 3),
                 round(p["w"], 3), round(p["h"], 3)), seats,
                "%s moved when the rim pass ran — it must only ADD" % p["stock"])

    def test_no_stone_is_used_twice(self):
        _, placed, _f, _s, _ = self._plate(self._mix(), tag="dup")
        stocks = [p["stock"] for p in placed]
        self.assertEqual(len(stocks), len(set(stocks)))


class JobPollThrottleTests(SimpleTestCase):
    """Polling a job must not spend the user's general API budget.

    An arrangement can run for half an hour, and the Result screen polls until
    it finishes. Charging those polls to the 1000/hour "user" bucket exhausted
    it mid-run, after which EVERY authenticated endpoint refused — /me and the
    form catalogue included — so a user could sign in successfully and then find
    the app would not open. That is one bug with two faces, and this pins it.
    """

    def test_the_poll_endpoint_uses_its_own_scope(self):
        from rest_framework.throttling import ScopedRateThrottle

        from .views import JobDetailView

        self.assertEqual(JobDetailView.throttle_scope, "job_poll")
        self.assertEqual(JobDetailView.throttle_classes, [ScopedRateThrottle])

    def test_the_poll_endpoint_is_not_charged_to_the_user_bucket(self):
        """Listing only ScopedRateThrottle REPLACES the defaults. If
        UserRateThrottle crept back into that list the lockout returns."""
        from rest_framework.throttling import UserRateThrottle

        from .views import JobDetailView

        for cls in JobDetailView.throttle_classes:
            self.assertFalse(issubclass(cls, UserRateThrottle),
                             "job polling is charged to the user bucket again")

    def test_the_scope_has_a_configured_rate(self):
        """A scope with no rate silently throttles to nothing."""
        from django.conf import settings

        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertIn("job_poll", rates)
        count, _, period = rates["job_poll"].partition("/")
        self.assertGreater(int(count), 1000,
                           "job_poll must exceed the general user rate or it is pointless")

    def test_other_endpoints_keep_the_default_throttles(self):
        """Only the poll is exempt — everything else stays rate-limited.

        APIView always defines `throttle_classes` from the settings default, so
        the test is whether a view OVERRODE it, not whether it has one.
        """
        from rest_framework.settings import api_settings

        from .views import ArrangementListView, JobsView, SeedImportView

        default = list(api_settings.DEFAULT_THROTTLE_CLASSES)
        for view in (JobsView, SeedImportView, ArrangementListView):
            self.assertEqual(list(view.throttle_classes), default,
                             f"{view.__name__} should use the project defaults")


class RotationDisplayTests(SimpleTestCase):
    """The turn printed on the plate must be the one the floor should perform.

    Reference only — nothing here feeds the packer — but a wrong number here
    sends an operator the wrong way round, which lands a cut corner facing the
    wrong side. So it is tested like any other output.
    """

    def test_stored_angles_are_converted_to_clockwise(self):
        """shapely.affinity.rotate turns COUNTER-clockwise for a positive angle,
        so a stored 90 is a 270 degree clockwise turn on the bench."""
        from .engine.pack_v2 import __name__ as _  # noqa: F401  (engine importable)

        from .engine_runner import D
        self.assertEqual(D.cw_degrees(0), 0)
        self.assertEqual(D.cw_degrees(90), 270)
        self.assertEqual(D.cw_degrees(180), 180)
        self.assertEqual(D.cw_degrees(270), 90)

    def test_conversion_is_safe_on_junk(self):
        from .engine_runner import D
        for v in (None, "", "abc"):
            self.assertEqual(D.cw_degrees(v), 0)

    def test_a_cut_seed_keeps_all_four_orientations(self):
        """Which way a ground corner points is the whole question, so a cut
        seed's angle is reported exactly."""
        from .engine_runner import D
        self.assertEqual(D.display_turn({"angle": 90, "irregular": True}), 270)
        self.assertEqual(D.display_turn({"angle": 180, "irregular": True}), 180)

    def test_a_plain_rectangle_is_folded_onto_half_a_turn(self):
        """180 degrees leaves a rectangle identical, so 270 and 90 are the same
        instruction — telling the floor 270 makes them do a three-quarter turn
        to reach a position a quarter turn gives."""
        from .engine_runner import D
        self.assertEqual(D.display_turn({"angle": 90, "irregular": False}), 90)
        self.assertEqual(D.display_turn({"angle": 180, "irregular": False}), 0)
        self.assertEqual(D.display_turn({"angle": 270, "irregular": False}), 90)

    def test_the_band_caption_reports_both_bands(self):
        from .engine_runner import D, P

        P.T_LO, P.T_HI = 0.67, 0.73
        P.W_LO, P.W_HI = 2.0, 12.0
        cap = D.band_caption()
        self.assertIn("0.67", cap)
        self.assertIn("0.73", cap)
        self.assertIn("2–12 mm", cap)

    def test_the_band_caption_handles_an_open_band(self):
        from .engine_runner import D, P

        P.T_LO, P.T_HI = 0.5, 0.8
        P.W_LO, P.W_HI = None, 12.0
        self.assertIn("≤ 12 mm", D.band_caption())
        P.W_LO, P.W_HI = 8.0, None
        self.assertIn("≥ 8 mm", D.band_caption())
        P.W_LO = P.W_HI = None
        self.assertIn("any", D.band_caption())


class ImplausibleMeasurementTests(SimpleTestCase):
    """Nonsense measurements are refused at IMPORT, before they can strand a run."""

    def _reason(self, L, W, H=0.70):
        from .services import _implausible

        return _implausible(L, W, H)

    def test_the_three_live_corrupt_rows_are_caught(self):
        """DOMI002328 / DOMI002296 / DOMI002278 as stored on the live table."""
        for L, W in ((1285.00, 9.03), (1288.00, 8.39), (1288.00, 8.03)):
            self.assertIsNotNone(self._reason(L, W), f"{L} x {W} should be refused")

    def test_the_message_points_at_the_decimal_point(self):
        self.assertIn("decimal point", self._reason(1285.00, 9.03))

    def test_the_largest_real_seed_in_stock_is_accepted(self):
        """23.98 x 23.44 mm is the biggest sound row on the live inventory —
        the guard must clear it by a wide margin, not squeak past it."""
        self.assertIsNone(self._reason(23.98, 23.44))

    def test_the_smallest_real_seed_in_stock_is_accepted(self):
        """2.01 mm is the narrowest sound row; the floor sits well below it."""
        self.assertIsNone(self._reason(12.0, 2.01))

    def test_an_ordinary_seed_is_accepted(self):
        self.assertIsNone(self._reason(12.85, 9.03))

    def test_zero_and_negative_are_refused(self):
        self.assertIsNotNone(self._reason(0.0, 9.0))
        self.assertIsNotNone(self._reason(12.0, 0.0))

    def test_a_bad_thickness_is_refused(self):
        self.assertIsNotNone(self._reason(12.0, 9.0, H=0.0))

    def test_either_side_can_trip_it(self):
        """The corrupt value can land in Length or in Width — the sheet's column
        order is not fixed, and `_mixed_landscape` swaps them anyway."""
        self.assertIsNotNone(self._reason(1285.0, 9.0))
        self.assertIsNotNone(self._reason(9.0, 1285.0))


class ImportRejectsImplausibleRowsTests(SimpleTestCase):
    """The guard is wired into import_seeds and costs only the offending row."""

    def _sheet(self, rows):
        wb = Workbook()
        ws = wb.active
        ws.append(["BatchNo", "StockNo", "Pcs", "Cts", "Length", "Width", "Height"])
        for r in rows:
            ws.append(list(r))
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_a_corrupt_row_is_skipped_and_the_rest_import(self):
        """One bad row must cost that row and nothing else — the same rule the
        missing-dimension check already follows."""
        from unittest import mock

        from .services import SeedImportService

        sheet = self._sheet([
            ("B1", "GOOD-1", 1, 1.0, 12.85, 9.03, 0.70),
            ("B1", "BAD", 1, 1.37, 1285.00, 9.03, 0.68),
            ("B1", "GOOD-2", 1, 1.0, 11.60, 11.00, 0.71),
        ])
        created = []
        with mock.patch.object(SeedImportService, "_ensure_batches", return_value=[]), \
             mock.patch("modules.production.services.BatchRepository.id_by_no", return_value={"B1": None}), \
             mock.patch("modules.production.services.SeedRepository.existing_stock_nos", return_value=set()), \
             mock.patch("modules.production.services.SeedRepository.bulk_create",
                        side_effect=lambda rows: created.extend(rows)):
            result = SeedImportService.import_seeds(sheet)

        self.assertEqual(result["imported"], 2)
        self.assertEqual([s.stock_no for s in created], ["GOOD-1", "GOOD-2"])
        reasons = {s["stock_no"]: s["reason"] for s in result["skipped"]}
        self.assertIn("BAD", reasons)
        self.assertIn("60 mm limit", reasons["BAD"])


class EagerJobDispatchTests(SimpleTestCase):
    """Local dev (CELERY_TASK_ALWAYS_EAGER) must still return the job id at once.

    `.delay()` under eager mode runs the task INSIDE the caller, so
    POST /production/jobs did not answer until the whole engine had finished —
    minutes on a real pool. The browser and the Vite proxy give up long before
    that, so the client never received a job id and nothing could be polled:
    plate generation appeared simply not to work on a local stack.
    """

    def _fake_task(self, record):
        import time

        def run(job_id):
            time.sleep(0.4)          # stand-in for the packing engine
            record.append(job_id)
        return run

    def test_create_job_returns_before_the_engine_finishes(self):
        import time
        from unittest import mock

        from django.test import override_settings

        from . import jobs as J

        done = []
        with override_settings(CELERY_TASK_ALWAYS_EAGER=True,
                               CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}):
            with mock.patch("modules.production.tasks.run_arrangement_job",
                            self._fake_task(done)):
                started = time.monotonic()
                job_id = J.create_job("arrange", {"plateD": 90})
                elapsed = time.monotonic() - started

                self.assertTrue(job_id)
                # The whole point: the POST does not wait for the engine.
                self.assertLess(elapsed, 0.3,
                                "create_job blocked on the task instead of "
                                "dispatching it to a thread")
                # The job row is readable straight away, so polling works.
                self.assertEqual(J.get_job(job_id)["status"], "queued")

                for _ in range(60):        # let the worker thread finish
                    if done:
                        break
                    time.sleep(0.05)
                self.assertEqual(done, [job_id])

    def test_a_real_broker_still_goes_through_celery(self):
        """Production is untouched — with eager off, dispatch must use .delay()."""
        from unittest import mock

        from django.test import override_settings

        from . import jobs as J

        # NOT locmem: with a real broker the job row has to live somewhere both
        # the web process and the worker can read, and `_assert_shared_cache`
        # rightly refuses a per-process cache. Any non-locmem backend satisfies
        # that guard, which is all this test needs.
        with override_settings(CELERY_TASK_ALWAYS_EAGER=False,
                               CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}):
            with mock.patch("modules.production.tasks.run_arrangement_job") as task:
                job_id = J.create_job("arrange", {"plateD": 90})
                task.delay.assert_called_once_with(job_id)


class SizeGradientTests(SimpleTestCase):
    """Larger seeds toward the middle, smaller toward the rim — and a MIXTURE.

    The defect this guards against: pick_level ranked height classes on
    (fits, stock), so the single best-stocked class won every row whatever its
    position. A live Ø70 plate came back using nothing under 9.42 mm although
    132 of its 236 stones were smaller than that. CENTRE_SIZE_BIAS could not fix
    it — it adds its term to `stock`, a total width in mm, and at a rim row the
    stock gap was 106.7 mm against a bias worth at most 18.4 mm.

    FIXTURE NOTE, learned the hard way. A handful of classes a whole millimetre
    apart proves nothing: the tolerance ties everything within its band, so
    three of five such classes tie at every row, stock decides, and BOTH
    rankings produce the same plate. The pool has to have the shape a real
    inventory has — many classes at LEVEL_BAND spacing with a stock peak in the
    middle of the range — before the two paths diverge at all.

    THESE ARE REQUIREMENT TESTS, NOT CHANGE DETECTORS, and there is deliberately
    no "the flag changes the output" case here. Whether it changes anything is
    POOL DEPENDENT: on a shallow pool or a plate with few rows the tolerance
    ties every candidate class, stock decides as before, and the two settings
    agree — correctly. A test asserting they must differ fails on exactly the
    fixtures a unit test can afford to build, and it would be asserting a
    property the feature does not have. That the knob bites on real stock is
    established by the three-plate validation table beside SIZE_GRADIENT_FRAC in
    demo_fill.py, which is the evidence to update when the inventory changes.
    """

    def _plate(self, pool, R=30.0, tag="grad"):
        import os
        import tempfile

        from .engine_runner import D
        tmp = tempfile.mkdtemp(prefix="grad-")
        return D.enhanced_plate_job(
            (list(pool), 1, 2 * R, R, 2.0, os.path.join(tmp, tag + ".png")))

    def _graded_pool(self):
        """Classes every 0.1 mm from 7.0 to 11.4, stock peaked near 9.4."""
        import math

        pool, n, h = [], 0, 7.0
        while h <= 11.45:
            k = round(h, 1)
            for i in range(2 + int(6 * math.exp(-((k - 9.4) ** 2) / 1.2))):
                pool.append(_rect_seed("S%d" % n, 9.0 + (i % 4) * 1.1, k))
                n += 1
            h += 0.1
        return pool

    def _sizes(self, placed):
        return {round(min(p["w"], p["h"]), 1) for p in placed}

    def _corr(self, placed):
        """Rank correlation of a seed's radius against its short side."""
        import math

        from shapely.geometry import Polygon as ShPoly

        rad, short = [], []
        for p in placed:
            c = ShPoly(p["poly"]).buffer(0).centroid
            rad.append(math.hypot(c.x, c.y))
            short.append(min(p["w"], p["h"]))

        def rk(xs):
            order = sorted(range(len(xs)), key=lambda i: xs[i])
            out = [0.0] * len(xs)
            i = 0
            while i < len(order):
                j = i
                while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                    j += 1
                for t in range(i, j + 1):
                    out[order[t]] = (i + j) / 2.0
                i = j + 1
            return out

        a, b = rk(rad), rk(short)
        n = len(a)
        ma, mb = sum(a) / n, sum(b) / n
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        da = math.sqrt(sum((x - ma) ** 2 for x in a))
        db = math.sqrt(sum((x - mb) ** 2 for x in b))
        return num / (da * db) if da and db else 0.0

    def test_the_plate_spends_more_than_one_height_class(self):
        """The live failure was 3 classes out of 25 available, everything else
        left in the drawer because one class out-stocked it at every row."""
        _, placed, _f, _s, _ = self._plate(self._graded_pool(), tag="mix")
        sizes = self._sizes(placed)
        self.assertGreaterEqual(
            len(sizes), 5,
            "the plate was built from %d height class(es) %s — the packer is "
            "spending one class and ignoring the rest of the user's range"
            % (len(sizes), sorted(sizes)))

    def test_bigger_seeds_sit_nearer_the_middle(self):
        """The gradient itself: size must fall off with radius."""
        _, placed, _f, _s, _ = self._plate(self._graded_pool(), tag="grad")
        c = self._corr(placed)
        self.assertLess(
            c, 0.0,
            "seed size does not fall off outward (rank correlation %+.3f); "
            "larger seeds belong toward the centre" % c)



class EmptyResultDiagnosisTests(SimpleTestCase):
    """When nothing matches, name the filter that actually did it.

    The screen used to guess, and guessed from the wrong field: any empty run
    with a seed-width band set was reported as "the seed width filter may be too
    narrow". On the live inventory a user asked 0.67-0.73 mm of stock that runs
    0.34-0.65 mm — thickness removed all 190 seeds and the width band matched
    every one of them — and the message still sent them to widen the width band.
    """

    def _apply(self, tlo, thi, plate_d=90):
        from .engine_runner import _apply_globals
        return _apply_globals({
            "mode": "mixed", "shape": "all", "squareTol": 0.05,
            "tLo": tlo, "tHi": thi, "plateD": plate_d, "margin": 5,
            "minSeed": 2, "clearance": 0, "grid": 0})

    def _run(self, rows, tlo=0.67, thi=0.73, w_lo=None, w_hi=None, plate_d=90):
        from .engine_runner import _blocks_from_seeds, _why_no_seeds, SHAPE_SETS
        self._apply(tlo, thi, plate_d)
        reject = {}
        blocks = _blocks_from_seeds(rows, SHAPE_SETS["all"], 0.05,
                                    w_lo=w_lo, w_hi=w_hi, oversize=[],
                                    reject=reject)
        return blocks, _why_no_seeds(reject)

    def test_thickness_is_named_when_thickness_is_the_cause(self):
        """The live case: every seed is inside the width band and outside the
        thickness range. Width must NOT be blamed."""
        rows = [_SeedRow("S%d" % i, 9.0, 8.0, 0.50) for i in range(10)]
        blocks, why = self._run(rows, tlo=0.67, thi=0.73, w_lo=7.0, w_hi=12.0)
        self.assertEqual(blocks, [])
        self.assertEqual(why["reason"], "thickness")
        self.assertEqual(why["removed"], 10)
        self.assertEqual(why["counts"]["width"], 0,
                         "the width band matched every seed and must not be "
                         "reported as the cause")
        self.assertEqual(why["thicknessSeen"], [0.5, 0.5],
                         "the message quotes the range the STOCK holds")

    def test_width_is_named_when_width_is_the_cause(self):
        rows = [_SeedRow("S%d" % i, 9.0, 8.0, 0.70) for i in range(10)]
        blocks, why = self._run(rows, tlo=0.67, thi=0.73, w_lo=20.0, w_hi=30.0)
        self.assertEqual(blocks, [])
        self.assertEqual(why["reason"], "width")
        self.assertEqual(why["counts"]["thickness"], 0)
        self.assertEqual(why["widthSeen"], [8.0, 8.0])

    def test_the_gate_that_removed_the_most_wins(self):
        """Mixed causes: whichever excluded more rows is the one worth naming."""
        rows = ([_SeedRow("T%d" % i, 9.0, 8.0, 0.20) for i in range(8)]
                + [_SeedRow("W%d" % i, 9.0, 8.0, 0.70) for i in range(2)])
        blocks, why = self._run(rows, tlo=0.67, thi=0.73, w_lo=20.0, w_hi=30.0)
        self.assertEqual(blocks, [])
        self.assertEqual(why["reason"], "thickness")
        self.assertEqual(why["counts"], {"thickness": 8, "width": 2,
                                         "oversize": 0, "shape": 0,
                                         "incomplete": 0})

    def test_an_oversize_row_is_named_as_oversize(self):
        """The live corrupt row shape: fits no orientation of the plate."""
        rows = [_SeedRow("BAD", 1285.0, 9.03, 0.70)]
        blocks, why = self._run(rows, tlo=0.67, thi=0.73)
        self.assertEqual(blocks, [])
        self.assertEqual(why["reason"], "oversize")

    def test_a_row_missing_a_measurement_is_named(self):
        rows = [_SeedRow("NOH", 9.0, 8.0, None)]
        blocks, why = self._run(rows, tlo=0.67, thi=0.73)
        self.assertEqual(blocks, [])
        self.assertEqual(why["reason"], "incomplete")

    def test_no_seeds_at_all_says_so(self):
        """An empty batch is not a filter problem and must not blame one."""
        blocks, why = self._run([], tlo=0.67, thi=0.73, w_lo=7.0, w_hi=12.0)
        self.assertEqual(blocks, [])
        self.assertEqual(why["reason"], "empty")
        self.assertEqual(why["examined"], 0)

    def test_counting_is_free_when_no_diagnosis_is_asked_for(self):
        """`reject` is optional — every existing caller passes nothing and must
        behave exactly as before."""
        from .engine_runner import _blocks_from_seeds, SHAPE_SETS
        self._apply(0.40, 0.60)
        rows = [_SeedRow("S%d" % i, 9.0, 8.0, 0.50) for i in range(5)]
        blocks = _blocks_from_seeds(rows, SHAPE_SETS["all"], 0.05)
        self.assertEqual(len(blocks), 5)


class SeedListLayoutTests(SimpleTestCase):
    """The seed list must stay readable however many seeds are on the plate.

    It used to be one column whatever its length, and a column cannot grow past
    the page: a Ø158 plate carries 150 seeds into a 9.6 inch panel, which is a
    0.06 inch row pitch under a 5.5 pt font, so the rows printed over each other.
    Nothing about that is specific to Ø158 — it is the seed COUNT, so any
    diameter hits it once enough seeds fit.
    """

    PANEL_H = 9.6 * 0.92          # the list area, less title and subtitle

    def test_every_row_has_room_for_its_text(self):
        """The invariant: pitch never falls below the readable minimum, at any
        seed count. This is what the single-column layout could not hold."""
        from .engine_runner import D

        for n in (1, 18, 36, 80, 150, 400, 1000):
            _ncols, per_col = D._legend_shape(n, self.PANEL_H)
            pitch = self.PANEL_H / per_col
            self.assertGreaterEqual(
                pitch, D.LEGEND_MIN_ROW_IN * 0.999,
                "%d seeds gives a %.3f in row pitch, under the %.3f in minimum "
                "— the list will print on top of itself"
                % (n, pitch, D.LEGEND_MIN_ROW_IN))

    def test_every_seed_gets_a_row(self):
        """Columns x rows must cover the list — no seed may be dropped off the
        end of a column."""
        from .engine_runner import D

        for n in (1, 17, 50, 150, 397):
            ncols, per_col = D._legend_shape(n, self.PANEL_H)
            self.assertGreaterEqual(
                ncols * per_col, n,
                "%d seeds only get %d x %d = %d slots"
                % (n, ncols, per_col, ncols * per_col))

    def test_a_short_list_stays_one_column(self):
        """Small plates must render exactly as they did — the fix is for lists
        that overflow, and it must not reformat the ones that never did."""
        from .engine_runner import D

        for n in (1, 18, 36, 50):
            ncols, _ = D._legend_shape(n, self.PANEL_H)
            self.assertEqual(ncols, 1, "%d seeds should not need columns" % n)
            self.assertEqual(D._legend_panel_in(n, self.PANEL_H),
                             D.LEGEND_MIN_PANEL_IN,
                             "%d seeds should not widen the panel" % n)

    def test_a_long_list_widens_the_panel_to_hold_its_columns(self):
        """Columns need somewhere to go: the panel grows with them, rather than
        the columns being squeezed into a fixed width and overlapping."""
        from .engine_runner import D

        ncols, per_col = D._legend_shape(150, self.PANEL_H)
        self.assertGreater(ncols, 1, "150 seeds must flow into columns")
        need = ncols * D._legend_col_in(D._legend_font_pt(per_col, self.PANEL_H))
        self.assertGreaterEqual(
            D._legend_panel_in(150, self.PANEL_H), need,
            "the panel is narrower than the columns it has to hold")

    def test_a_column_is_wide_enough_for_its_own_text_at_every_count(self):
        """The defect a FIXED column width caused, and the reason the width is
        now derived from the font.

        The font is sized from the row pitch, so it GROWS when a column holds
        fewer rows — and a bigger font needs a wider column. At 3.4 inches flat,
        a 71-seat Ø110 plate drew 8.6 pt text needing 3.44 in and printed its
        rotation angle underneath the next column's number. Fewer seeds was
        worse, which is why a 150-seat plate looked fine. Sweeping every count
        found 48 broken: 56-84, 111-126, 166-168.
        """
        from .engine_runner import D

        for n in list(range(2, 200)) + [250, 300, 400]:
            ncols, per_col = D._legend_shape(n, self.PANEL_H)
            if ncols < 2:
                continue                      # one column owns the whole panel
            colw = D._legend_panel_in(n, self.PANEL_H) / ncols
            font = D._legend_font_pt(per_col, self.PANEL_H)
            text = D.LEGEND_ENTRY_CHARS * font * D.LEGEND_EM_PER_CHAR / 72.0
            self.assertLessEqual(
                (1.0 - D.LEGEND_TEXT_FRAC) * colw + text, colw,
                "%d seeds: %.1f pt text needs more than the %.2f in column, so "
                "one column prints over the next" % (n, font, colw))

    def test_columns_are_balanced(self):
        """A stub last column wastes the width it cost — 150 over 3 columns is
        50 each, not 55/55/40."""
        from .engine_runner import D

        ncols, per_col = D._legend_shape(150, self.PANEL_H)
        last = 150 - per_col * (ncols - 1)
        self.assertGreater(last, 0, "the last column is empty")
        self.assertLessEqual(
            per_col - last, per_col * 0.5,
            "columns are lopsided: %d x %d with %d in the last"
            % (ncols, per_col, last))


class SetPlateActiveTests(TransactionTestCase):
    """Retiring a plate name — the app's soft delete, and the only one live can use.

    Live runs under IIS, whose WebDAV module answers PUT and DELETE with 405
    before Django sees them, so Plate Master's edit and delete and Finalization's
    "Return all" are all unreachable there while every POST works. This endpoint
    is POST in BOTH directions for that reason: a one-way call would let a plate
    be deactivated on live with no way to restore it.

    A hard delete would be wrong regardless of the verb. MST_SeedPlate carries no
    foreign keys, so removing a row would silently orphan every arrangement still
    naming it rather than being refused.
    """

    available_apps = ["modules.production", "modules.access", "modules.accounts",
                      "django.contrib.auth", "django.contrib.contenttypes"]

    @classmethod
    def _unmanaged(cls):
        from django.apps import apps
        return [m for m in apps.get_app_config("production").get_models()
                if not m._meta.managed]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.db import connection
        with connection.schema_editor() as se:
            for m in cls._unmanaged():
                se.create_model(m)

    @classmethod
    def tearDownClass(cls):
        from django.db import connection
        with connection.schema_editor() as se:
            for m in cls._unmanaged():
                se.delete_model(m)
        super().tearDownClass()

    def setUp(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        from .models import SeedPlate
        SeedPlate.objects.all().delete()
        self.SeedPlate = SeedPlate
        self.user = get_user_model().objects.create_superuser("sa", "sa@x.y", "pw12345!")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _post(self, plate_id, active):
        return self.client.post("/api/production/plates/set-active",
                                {"plateId": plate_id, "active": active}, format="json")

    def test_deactivating_takes_the_plate_out_of_the_dropdown(self):
        """`is_active` is not decoration — it is the filter behind the plate names
        Finalization offers, which is what makes this a delete from that screen."""
        p = self.SeedPlate.objects.create(plate_name="P-A", diameter=90, is_active=True)
        self.assertEqual(self._post(p.plate_id, False).status_code, 200)
        p.refresh_from_db()
        self.assertFalse(p.is_active)
        names = [q["plateName"] for q in self.client.get("/api/production/plates").json()]
        self.assertNotIn("P-A", names, "a deactivated plate must not be offered")

    def test_it_is_reversible(self):
        """The reason this is POST both ways: on live there is no PUT to turn a
        plate back on with."""
        p = self.SeedPlate.objects.create(plate_name="P-B", diameter=90, is_active=False)
        self.assertEqual(self._post(p.plate_id, True).status_code, 200)
        p.refresh_from_db()
        self.assertTrue(p.is_active)

    def test_the_row_survives_so_history_is_intact(self):
        """Soft, not hard: MST_SeedPlate has no foreign keys, so a real delete
        would orphan the arrangements naming this plate instead of failing."""
        p = self.SeedPlate.objects.create(plate_name="P-C", diameter=90, is_active=True)
        self._post(p.plate_id, False)
        self.assertTrue(self.SeedPlate.objects.filter(pk=p.plate_id).exists())

    def test_a_plate_still_holding_stock_is_refused(self):
        """Deactivating must never move inventory. A plate an arrangement is
        still using has to be RELEASED first — that is the action that hands the
        seeds back, and it stays exactly as it was."""
        p = self.SeedPlate.objects.create(plate_name="P-D", diameter=90,
                                          is_active=True, is_used=True)
        r = self._post(p.plate_id, False)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("Release it first", r.content.decode())
        p.refresh_from_db()
        self.assertTrue(p.is_active, "a refused call must not have changed anything")

    def test_it_leaves_the_inventory_flags_alone(self):
        """Only ISActive moves. is_used/is_released belong to assign and release."""
        p = self.SeedPlate.objects.create(plate_name="P-E", diameter=90, is_active=True,
                                          is_used=False, is_released=True)
        self._post(p.plate_id, False)
        p.refresh_from_db()
        self.assertFalse(p.is_active)
        self.assertFalse(p.is_used)
        self.assertTrue(p.is_released, "release state must be untouched")

    def test_an_unknown_plate_is_a_clean_400(self):
        r = self._post(999999, False)
        self.assertEqual(r.status_code, 400, r.content)

    def test_only_post_is_accepted(self):
        """The whole point of the endpoint: live's IIS blocks PUT and DELETE."""
        from modules.production.views import SetPlateActiveView
        self.assertEqual(sorted(SetPlateActiveView().allowed_methods), ["OPTIONS", "POST"])
