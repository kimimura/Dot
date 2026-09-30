# Build-time only: python tools/trace_avatar.py <image> --out trace.json, then run build_avatar.py
import argparse
import json
import os
import sys
from collections import deque

import numpy as np
from PIL import Image

VIEW_W, VIEW_H = 160, 184
TOP_Y, FOOT_Y = 6.0, 167.0
CENTRE_X = 80.0
MIN_PANEL_PX = 40
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
MOORE = ((-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1))

# Panel indices are stable for this reference (sorted by area, descending).
GROUPS = {
    "head":  [1, 0, 4, 15, 16],
    "eye-l": [9],
    "eye-r": [8],
    "arm-l": [22, 5, 13, 10, 27],
    "arm-r": [21, 6, 14, 11, 28],
    "leg-l": [37, 32, 33, 38, 24, 25],
    "leg-r": [36, 34, 30, 39, 23, 26],
    "body":  [7, 42, 43, 2, 12, 19, 20, 40, 41, 17, 18, 29, 35, 31, 3],
}
GLASS = {8, 9, 12}
GOLD = {0, 4, 7, 2, 17, 18, 29, 40, 41, 42, 43, 27, 28, 23, 24, 25, 26}
DARK = {15, 16}
KEYLINE_PX = int(os.environ.get("KEYLINE_PX", 6))    # outer line, source px. Reference uses ~15; 6 reads cleaner at 136px
PANEL_GROW = int(os.environ.get("PANEL_GROW", 0))    # thins inner lines by 2x this; above 0 the finest lines vanish


def dilate(mask, r):
    m = mask.copy()
    for _ in range(r):
        out = m.copy()
        out[1:, :] |= m[:-1, :]
        out[:-1, :] |= m[1:, :]
        out[:, 1:] |= m[:, :-1]
        out[:, :-1] |= m[:, 1:]
        m = out
    return m


def colour_of(i):
    if i in GLASS:
        return "glass"
    if i in GOLD:
        return "gold"
    if i in DARK:
        return "dark"
    return "red"


def load(path):
    g = np.asarray(Image.open(path).convert("L"))
    return g, g >= 128


def label(mask):
    h, w = mask.shape
    lab = np.full((h, w), -1, np.int32)
    out, tag = [], 0

    def flood(sy, sx, t):
        q = deque([(sy, sx)])
        lab[sy, sx] = t
        px = []
        while q:
            y, x = q.popleft()
            px.append((y, x))
            for dy, dx in N4:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and lab[ny, nx] == -1:
                    lab[ny, nx] = t
                    q.append((ny, nx))
        return px

    flood(0, 0, 0)
    for y in range(h):
        for x in np.where(mask[y] & (lab[y] == -1))[0]:
            tag += 1
            px = flood(y, int(x), tag)
            if len(px) >= MIN_PANEL_PX:
                out.append((len(px), tag, px))
    out.sort(reverse=True)
    return lab, out


def trace(mask):
    h, w = mask.shape
    start = None
    for y in range(h):
        xs = np.where(mask[y])[0]
        if len(xs):
            start = (y, int(xs[0]))
            break
    if start is None:
        return []
    contour = [start]
    cur, back = start, (start[0], start[1] - 1)
    limit = 4 * int(mask.sum()) + 64
    for _ in range(limit):
        bi = MOORE.index((back[0] - cur[0], back[1] - cur[1]))
        nxt = None
        for k in range(1, 9):
            dy, dx = MOORE[(bi + k) % 8]
            ny, nx = cur[0] + dy, cur[1] + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx]:
                nxt = (ny, nx)
                back = (cur[0] + MOORE[(bi + k - 1) % 8][0], cur[1] + MOORE[(bi + k - 1) % 8][1])
                break
        if nxt is None:
            break
        cur = nxt
        if cur == start:
            break
        contour.append(cur)
    return contour


def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    a, b = np.array(pts[0], float), np.array(pts[-1], float)
    ab = b - a
    n = np.hypot(*ab)
    P = np.array(pts, float)
    if n < 1e-9:
        d = np.hypot(*(P - a).T)
    else:
        V = P - a; d = np.abs(ab[0] * V[:, 1] - ab[1] * V[:, 0]) / n
    i = int(d.argmax())
    if d[i] > eps:
        return rdp(pts[:i + 1], eps)[:-1] + rdp(pts[i:], eps)
    return [pts[0], pts[-1]]


def simplify_closed(contour, eps):
    if len(contour) < 4:
        return contour
    half = len(contour) // 2
    a = rdp(contour[:half + 1], eps)
    b = rdp(contour[half:] + [contour[0]], eps)
    return a[:-1] + b[:-1]


def mapper(bbox):
    x0, y0, x1, y1 = bbox
    k = (FOOT_Y - TOP_Y) / (y1 - y0)
    cx = (x0 + x1) / 2.0
    return lambda x, y: (CENTRE_X + (x - cx) * k, TOP_Y + (y - y0) * k), k


def to_path(contour, fn, dp=2):
    if len(contour) < 3:
        return ""
    pts = [fn(x, y) for y, x in contour]
    head = "M%.*f %.*f" % (dp, pts[0][0], dp, pts[0][1])
    rest = "".join("L%.*f %.*f" % (dp, px, dp, py) for px, py in pts[1:])
    return head + rest + "Z"


def sub(mask, bbox, pad=2):
    x0, y0, x1, y1 = bbox
    h, w = mask.shape
    y0, y1 = max(0, y0 - pad), min(h - 1, y1 + pad)
    x0, x1 = max(0, x0 - pad), min(w - 1, x1 + pad)
    return mask[y0:y1 + 1, x0:x1 + 1], (x0, y0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out", default="trace.json")
    ap.add_argument("--eps", type=float, default=1.1, help="RDP tolerance in source pixels")
    a = ap.parse_args()

    g, paper = load(a.image)
    h, w = g.shape
    lab, comps = label(paper)
    print(f"panels: {len(comps)}")
    inner = np.isin(lab, [c[1] for c in comps])
    ys, xs = np.where(inner)
    e = KEYLINE_PX
    fig = (int(xs.min()) - e, int(ys.min()) - e, int(xs.max()) + e, int(ys.max()) + e)
    fn, k = mapper(fig)
    print(f"image {w}x{h}   drawn extent {fig}   keyline {KEYLINE_PX}px  grow {PANEL_GROW}px   scale {k:.5f} units/px")

    # silhouette = everything that is not the outer background
    solid = lab != 0
    sil = simplify_closed(trace(solid), a.eps)
    print(f"silhouette: {len(sil)} pts")

    # each limb's outline is its panels grown by the keyline, so the line rotates with the limb
    tag_of = {i: comps[i][1] for i in range(len(comps))}
    outlines = {}
    for gname, idxs in GROUPS.items():
        m = np.zeros_like(solid)
        for i in idxs:
            if i < len(comps):
                m |= (lab == tag_of[i])
        c = simplify_closed(trace(dilate(m, KEYLINE_PX)), a.eps)
        outlines[gname] = to_path(c, fn)
        print(f"  outline {gname:6} {len(idxs):>2} panels -> {len(c):>3} pts")

    panels = []
    for i, (n, tag, px) in enumerate(comps):
        m = lab == tag
        ys_, xs_ = np.where(m)
        bb = (int(xs_.min()), int(ys_.min()), int(xs_.max()), int(ys_.max()))
        smask, (ox, oy) = sub(m, bb, pad=2 + PANEL_GROW)
        if PANEL_GROW:
            smask = dilate(smask, PANEL_GROW)
        c = trace(smask)
        c = [(y + oy, x + ox) for y, x in c]
        c = simplify_closed(c, a.eps)
        cx, cy = fn(float(xs_.mean()), float(ys_.mean()))
        p0 = fn(bb[0], bb[1])
        p1 = fn(bb[2], bb[3])
        grp = next((g for g, v in GROUPS.items() if i in v), "body")
        panels.append({
            "i": i, "area": int(n), "pts": len(c),
            "group": grp, "colour": colour_of(i),
            "bbox_px": bb,
            "bbox": [round(p0[0], 2), round(p0[1], 2), round(p1[0], 2), round(p1[1], 2)],
            "centroid": [round(cx, 2), round(cy, 2)],
            "d": to_path(c, fn),
        })

    ungrouped = [p["i"] for p in panels if not any(p["i"] in v for v in GROUPS.values())]
    if ungrouped:
        print(f"  WARNING unassigned panels -> body: {ungrouped}")

    data = {
        "source": os.path.basename(a.image),
        "figure_px": fig, "scale": k,
        "viewBox": [0, 0, VIEW_W, VIEW_H],
        "silhouette": to_path(sil, fn),
        "outlines": outlines,
        "panels": panels,
    }
    with open(a.out, "w", encoding="utf8") as f:
        json.dump(data, f, indent=1)
    tot = len(data["silhouette"]) + sum(len(p["d"]) for p in panels)
    print(f"wrote {a.out}   {len(panels)} panels   {tot/1024:.1f} KB of path data")


if __name__ == "__main__":
    sys.exit(main())
