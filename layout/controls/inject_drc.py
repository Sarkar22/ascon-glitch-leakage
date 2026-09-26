# SPDX-License-Identifier: Apache-2.0
"""KLayout batch script: copy a GDS and add two deliberate DRC violations (negative control).

  klayout -b -r layout/controls/inject_drc.py -rd gds_in=<clean.gds> -rd gds_out=<bad.gds> \
      -rd json_out=<injected.json>

Adds, in the top cell, at free spots inside the standard-cell rows (the bounding box of the placed
cell instances, 1 um in from its edge; no met1, met2, mcon or via1 within 0.4 um):
  met1_spacing   two met1 rectangles 0.50 x 0.40 um, 0.07 um apart (rule m1.2: 0.14 um). Each is
                 wide enough (m1.1) and large enough (m1.6), so spacing is the only rule broken.
  via1_enclosure one 0.15 um via1 cut with met1 extending 0.03 um past its left and right edges and
                 0.15 um past the others (rule via.4a: 0.055 um; the two short sides are opposite,
                 so via.5a, two adjacent sides, is met), under a met2 pad with 0.15 um on every
                 side (m2.4 and m2.5 met). Only the met1 enclosure is broken.
Coordinates are on the 5 nm grid. Nothing else in the layout is changed. json_out lists every
added shape and the bounding box of each structure, in um, for layout/neg_controls.py.
Needs KLayout >= 0.27 (Python), as in the OpenLane v1 image.
"""
import json

import pya

gds_in = globals().get("gds_in")
gds_out = globals().get("gds_out")
json_out = globals().get("json_out")
if not (gds_in and gds_out and json_out):
    raise SystemExit("usage: klayout -b -r inject_drc.py -rd gds_in=... -rd gds_out=... "
                     "-rd json_out=...")

MET1, MET2, VIA1, MCON = (68, 20), (69, 20), (68, 44), (67, 44)
BLOCKING = (MET1, MET2, VIA1, MCON, (68, 16), (69, 16))    # drawing and pin shapes
MARGIN = 0.4       # um of clearance from any existing shape on those layers
EDGE = 1.0         # um kept free inside the edge of the cell rows
APART = 5.0        # um between the two structures
GRID = 0.005

ly = pya.Layout()
ly.read(gds_in)
top = ly.top_cell()
dbu = ly.dbu


def d(um):
    return int(round(um / dbu))


def snap(um):
    return round(round(um / GRID) * GRID, 3)


blocked = pya.Region()
for ld in BLOCKING:
    li = ly.find_layer(*ld)
    if li is not None:
        blocked += pya.Region(top.begin_shapes_rec(li))
blocked.merge()
rows = pya.Box()
for inst in top.each_inst():
    rows += inst.bbox()                      # the placed standard cells (taps, decaps, fill incl.)
rows = pya.DBox(rows.left * dbu, rows.bottom * dbu, rows.right * dbu, rows.top * dbu)
inner = pya.Region(pya.Box(d(rows.left + EDGE), d(rows.bottom + EDGE), d(rows.right - EDGE),
                           d(rows.top - EDGE)))


def find_spot(w, h, avoid):
    """Lower-left corner (um) of a free w x h box, scanning rows bottom-up, left to right."""
    free = inner - avoid.sized(d(MARGIN))
    core = free.sized(-d(w / 2 + 0.01), -d(h / 2 + 0.01))       # possible box centres
    cands = sorted((p.bbox() for p in core.each()), key=lambda b: (b.bottom, b.left))
    for b in cands:
        for cx, cy in ((b.center().x, b.center().y), (b.left, b.bottom), (b.right, b.top)):
            x0, y0 = snap(cx * dbu - w / 2), snap(cy * dbu - h / 2)
            box = pya.Region(pya.Box(d(x0), d(y0), d(x0 + w), d(y0 + h)))
            if (box - free).is_empty():
                return x0, y0
    raise SystemExit("no free %.2f x %.2f um spot found" % (w, h))


def add(layer, x1, y1, x2, y2, shapes):
    top.shapes(ly.layer(*layer)).insert(pya.Box(d(x1), d(y1), d(x2), d(y2)))
    shapes.append({"layer": "%d/%d" % layer, "box_um": [round(v, 3) for v in (x1, y1, x2, y2)]})


out = []
avoid = blocked.dup()

# 1. met1 spacing: two rectangles 0.07 um apart
w, h, gap = 0.50, 0.40, 0.07
x0, y0 = find_spot(2 * w + gap, h, avoid)
shapes = []
add(MET1, x0, y0, x0 + w, y0 + h, shapes)
add(MET1, x0 + w + gap, y0, x0 + 2 * w + gap, y0 + h, shapes)
bbox = [x0, y0, round(x0 + 2 * w + gap, 3), round(y0 + h, 3)]
out.append({"name": "met1_spacing", "rule": "m1.2 met1 spacing >= 0.14 um",
            "drawn": "0.07 um gap between two 0.50 x 0.40 um met1 rectangles",
            "shapes": shapes, "bbox_um": bbox})
avoid += pya.Region(pya.Box(d(bbox[0]), d(bbox[1]), d(bbox[2]), d(bbox[3]))).sized(d(APART))

# 2. via1 with too little met1 enclosure on two opposite sides
cut, enc_x, enc_y, enc_m2 = 0.15, 0.03, 0.15, 0.15
size = cut + 2 * enc_m2
x0, y0 = find_spot(size, size, avoid)
vx, vy = x0 + enc_m2, y0 + enc_m2                       # lower-left corner of the cut
shapes = []
add(VIA1, vx, vy, vx + cut, vy + cut, shapes)
add(MET1, vx - enc_x, vy - enc_y, vx + cut + enc_x, vy + cut + enc_y, shapes)
add(MET2, x0, y0, x0 + size, y0 + size, shapes)
out.append({"name": "via1_enclosure", "rule": "via.4a met1 enclosure of via1 >= 0.055 um",
            "drawn": "met1 enclosure 0.03 um (left, right), 0.15 um (bottom, top); met2 0.15 um",
            "shapes": shapes, "bbox_um": [round(v, 3) for v in (x0, y0, x0 + size, y0 + size)]})

ly.write(gds_out)
with open(json_out, "w") as f:
    json.dump({"gds_in": gds_in.split("/")[-1], "gds_out": gds_out.split("/")[-1],
               "top_cell": top.name, "dbu_um": dbu, "margin_um": MARGIN,
               "cell_rows_bbox_um": [round(v, 3) for v in (rows.left, rows.bottom, rows.right,
                                                           rows.top)],
               "injected": out}, f, indent=1)
print("injected %d structures -> %s" % (len(out), gds_out))
