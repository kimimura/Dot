# Build-time only: python tools/build_avatar.py trace.json --out avatar.js, then paste into static/robot.js
import argparse
import json

ORDER_LEGS = ["leg-l", "leg-r"]
ORDER_ARMS = ["arm-l", "arm-r"]
REACTOR = 12          # panel index of the arc reactor -> .antenna-ball
IND = "      "


def bbox_of(panels, idxs):
    b = [p["bbox"] for p in panels if p["i"] in idxs]
    return [min(v[0] for v in b), min(v[1] for v in b),
            max(v[2] for v in b), max(v[3] for v in b)]


def paths(panels, group, skip=()):
    out = []
    for p in panels:
        if p["group"] != group or p["i"] in skip:
            continue
        out.append(f'<path class="pl {p["colour"]}" d="{p["d"]}"/>')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--out", default="avatar.js")
    a = ap.parse_args()
    T = json.load(open(a.trace, encoding="utf8"))
    P = T["panels"]
    OL = T["outlines"]
    by_i = {p["i"]: p for p in P}

    eyeL, eyeR = by_i[9]["bbox"], by_i[8]["bbox"]
    cen = lambda b: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    pl, pr = cen(eyeL), cen(eyeR)
    headb = bbox_of(P, set(g for g in [1, 0, 4, 15, 16]))
    armlb, armrb = bbox_of(P, {22, 5, 13, 10, 27}), bbox_of(P, {21, 6, 14, 11, 28})
    leglb, legrb = bbox_of(P, {37, 32, 33, 38, 24, 25}), bbox_of(P, {36, 34, 30, 39, 23, 26})
    glove = by_i[28]["bbox"]
    r = lambda v: round(v, 1)

    piv = {
        "rig": [80, 168],
        "body": [80, 138],
        "head": [80, r(headb[3] - 2)],
        "armL": [r((armlb[0] + armlb[2]) / 2), r(armlb[1] + 3)],
        "armR": [r((armrb[0] + armrb[2]) / 2), r(armrb[1] + 3)],
        "legL": [r((leglb[0] + leglb[2]) / 2), r(leglb[1] + 2)],
        "legR": [r((legrb[0] + legrb[2]) / 2), r(legrb[1] + 2)],
        "eyeL": [r(pl[0]), r(pl[1])],
        "eyeR": [r(pr[0]), r(pr[1])],
        "browL": [r(pl[0]), r(eyeL[1] - 5)],
        "browR": [r(pr[0]), r(eyeR[1] - 5)],
        "page": [r((glove[0] + glove[2]) / 2), r(glove[1])],
        "shadow": [80, 174],
    }

    L, R = [], []
    L.append('<svg class="bot robot" viewBox="0 0 160 184" aria-hidden="true">${DEFS}')
    L.append('  <g class="rig">')
    L.append('    <g class="legs">')
    for g in ORDER_LEGS:
        L.append(f'      <g class="{g}"><path class="ol" d="{OL[g]}"/>')
        L += [IND + "  " + s for s in paths(P, g)]
        L.append("      </g>")
    L.append("    </g>")
    L.append('    <g class="body">')
    for g in ORDER_ARMS:
        L.append(f'      <g class="arm {g}"><path class="ol" d="{OL[g]}"/>')
        L += [IND + "  " + s for s in paths(P, g)]
        if g == "arm-r":
            # the page rotates about its pivot, so draw it at real coordinates on the glove
            px, py = piv["page"]
            rx0, ry0 = r(px - 15), r(py - 19)
            L.append(IND + f'  <g class="page"><rect x="{rx0}" y="{ry0}" width="30" height="38" rx="3"/>'
                           f'<path d="M{r(rx0+6)} {r(ry0+11)}h18M{r(rx0+6)} {r(ry0+18)}h18'
                           f'M{r(rx0+6)} {r(ry0+25)}h12"/></g>')
        L.append("      </g>")

    L.append(f'      <path class="ol" d="{OL["body"]}"/>')
    L += [IND + s for s in paths(P, "body", skip={REACTOR})]
    rb = by_i[REACTOR]["bbox"]
    rcx, rcy = (rb[0] + rb[2]) / 2, (rb[1] + rb[3]) / 2
    L.append(f'      <circle class="antenna-glow" cx="{r(rcx)}" cy="{r(rcy)}" r="{r((rb[2]-rb[0]))}"/>')
    L.append(f'      <path class="antenna-ball" d="{by_i[REACTOR]["d"]}"/>')

    L.append('      <g class="head">')
    L.append(f'        <path class="ol" d="{OL["head"]}"/>')
    L += [IND + "  " + s for s in paths(P, "head")]
    # no eye outline: the head outline shows through around the eye, which also makes blinks read right
    L.append('        <g class="eyes">')
    for cls, idx in (("eye-l", 9), ("eye-r", 8)):
        p = by_i[idx]
        b = p["bbox"]
        mid = (b[1] + b[3]) / 2
        # pupil is a small glint, so cursor tracking moves the glint, not the whole eye
        L.append(f'          <g class="eye {cls}"><path class="eyeball" d="{p["d"]}"/>'
                 f'<ellipse class="pupil" cx="{r((b[0]+b[2])/2)}" cy="{r(mid)}" rx="{r((b[2]-b[0])*0.17)}" ry="{r((b[3]-b[1])*0.3)}"/>'
                 f'<path class="eye-happy" d="M{r(b[0]+1)} {r(b[3])} Q{r((b[0]+b[2])/2)} {r(b[1]-3)} {r(b[2]-1)} {r(mid)}"/></g>')
    L.append("        </g>")
    for cls, b, c in (("brow-l", eyeL, pl), ("brow-r", eyeR, pr)):
        L.append(f'        <line class="brow {cls}" x1="{r(b[0]+1)}" y1="{r(b[1]+1.5)}" '
                 f'x2="{r(b[2]-1)}" y2="{r(b[1]+0.5)}"/>')
    L.append("      </g>")
    L.append("    </g>${FX}")
    L.append("  </g>")
    L.append("</svg>")

    js = ("  function markupIronman() {\n    return `\n" + "\n".join(L) + "`;\n  }\n")
    pv = ("    ironman: { " + ", ".join(f"{k}: [{v[0]}, {v[1]}]" for k, v in piv.items()) + " },\n")
    with open(a.out, "w", encoding="utf8") as f:
        f.write(js + "\n" + pv)
    print(f"wrote {a.out}   markup {len(js)/1024:.1f} KB")
    print("\npivots derived from the trace:")
    for k, v in piv.items():
        print(f"  {k:7} {v}")


if __name__ == "__main__":
    main()
