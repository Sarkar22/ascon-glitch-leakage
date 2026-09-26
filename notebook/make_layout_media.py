# SPDX-License-Identifier: Apache-2.0
"""Small copies of the layout images for the notebook (media/, shipped with it).

The notebook's section 6 shows the N and DA layouts. The originals in results/layout/ come from
layout/run_klayout.sh (KLayout renders, 1000 x 1000 px, all drawn layers in the PDK colours). This
script writes, for V = N and DA:
  media/layout_<V>.png      the KLayout render, halved to 500 x 500 px by 2 x 2 averaging and
                            stored with a 64-colour palette (about 60 kB instead of 430 kB)
and prints the sizes. The placement maps below them are drawn from data
(data/layout__placement_<V>.csv), not from images. Needs matplotlib and Pillow (the cac-sca image
has both):

  bash sim/docker_run.sh python3 notebook/make_layout_media.py
"""
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, "results", "layout")
MEDIA = os.path.join(HERE, "media")
VARIANTS = ("N", "DA")


def halve(img):
    """2 x 2 block average of an (h, w, c) float image (odd edges dropped)."""
    h, w = img.shape[0] // 2 * 2, img.shape[1] // 2 * 2
    x = img[:h, :w]
    return x.reshape(h // 2, 2, w // 2, 2, -1).mean(axis=(1, 3))


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    os.makedirs(MEDIA, exist_ok=True)
    for v in VARIANTS:
        img = plt.imread(os.path.join(SRC, "%s_layout.png" % v))
        out = os.path.join(MEDIA, "layout_%s.png" % v)
        small = np.round(np.clip(halve(img)[:, :, :3], 0, 1) * 255).astype(np.uint8)
        Image.fromarray(small).quantize(colors=64).save(out, optimize=True)
        print("%-28s %7.1f kB" % (os.path.relpath(out, REPO), os.path.getsize(out) / 1e3))


if __name__ == "__main__":
    main()
