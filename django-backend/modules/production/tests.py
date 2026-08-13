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
