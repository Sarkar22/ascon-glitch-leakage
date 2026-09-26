# SPDX-License-Identifier: Apache-2.0
"""KLayout batch script: layer-coloured PNG of a GDS (run by layout/run_images.sh).

  klayout -b -r layout/render.py -rd gds=<file.gds> -rd lyp=<sky130A.lyp> -rd out=<file.png> \
      [-rd width=1600] [-rd layers=all|routing]

layers=all shows every drawn layer with the PDK's colours; layers=routing hides the device layers
(wells, diffusion, implants, poly) so the metal routing and the cell pins stand out.
Needs KLayout >= 0.28 (standalone LayoutView), as in the OpenLane v1 image.
"""
import pya

gds = globals().get("gds")
lyp = globals().get("lyp")
out = globals().get("out")
width = int(globals().get("width", "1600"))
mode = globals().get("layers", "all")
if not (gds and lyp and out):
    raise SystemExit("usage: klayout -b -r render.py -rd gds=... -rd lyp=... -rd out=...")

ROUTING = ("li1", "mcon", "met1", "via", "met2", "via2", "met3", "via3", "met4", "via4", "met5")

view = pya.LayoutView()
view.load_layout(gds, True)
view.load_layer_props(lyp)
view.max_hier()
view.set_config("background-color", "#ffffff")
view.set_config("grid-visible", "false")
view.set_config("text-visible", "false")
view.set_config("bitmap-oversampling", "2")
view.set_config("default-font-size", "0")

it = view.begin_layers()
while not it.at_end():
    lp = it.current()
    name = (lp.source_name or lp.name or "").lower()
    base = name.split(".")[0].split(" ")[0]          # "met1.drawing - 68/20" -> met1, drawing
    purpose = name.split(".")[1].split(" ")[0] if "." in name else "drawing"
    visible = lp.visible
    if mode == "routing":
        visible = base in ROUTING and purpose in ("drawing", "pin")
    # hide the layers that only clutter a picture of a small block
    if base in ("areaid", "prbndry", "prboundary", "boundary", "diff_fill", "poly_fill",
                "metal_fill", "npc", "hvtp", "lvtn", "psdm", "nsdm", "tap_fill", "cfom", "cp1m",
                "ctm1", "cmm1", "cmm2", "cmm3", "cmm4", "cmm5", "cviam", "cviam2", "cviam3",
                "cviam4", "cnwm", "cpdm"):
        visible = False
    if purpose in ("label", "boundary", "res", "cut", "short", "gate", "probe", "mask",
                   "blockage", "fill"):
        visible = False
    lp.visible = visible
    view.set_layer_properties(it, lp)
    it.next()

view.zoom_fit()
box = view.box()
height = max(200, int(round(width * box.height() / box.width())))
view.save_image_with_options(out, width, height, 0, 0, 0, pya.DBox(), False)
print("wrote %s (%d x %d)" % (out, width, height))
