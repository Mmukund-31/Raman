"""Data for the simple, picture-first report: everything here is copied or rescaled from computed results.

build(analysis, sections) -> {
  confidence: {level 0-3, label, reason}          one glance answer to "how sure?"
  overlay:    sample + best-match reference curves (each scaled to its own maximum) and the shared peaks
  candidates: the closest materials with their similarity and the threshold needed to name one
  checks:     plain-language pass/fail list of the quality gate
}
"""
import numpy as np

from . import quality

LEVELS = ["Can't tell", "Demo only", "Likely", "Confident"]


def _down(x, y, n=1000):
    step = max(1, len(x) // n)
    return list(x[::step]), list(y[::step])


def _scaled(y):
    y = np.asarray(y, float)
    m = float(np.max(y)) if y.size else 0.0
    return (y / m).round(4).tolist() if m > 0 else y.tolist()


def _peak_fraction(m):
    pa = m.get("peak_agreement") or {}
    n = pa.get("reference_peaks_in_overlap") or 0
    return (len(pa.get("matched", [])), n)


def confidence(a):
    ms = a["matches"]
    if a["status"] != "ok" or not ms:
        return {"level": 0, "label": LEVELS[0], "reason": "The checks below were not all passed, so no material is named."}
    t = ms[0]
    if t.get("category") != "measured":
        return {"level": 1, "label": LEVELS[1], "reason": "The closest reference is simulated, so this cannot identify a real material."}
    k, n = _peak_fraction(t)
    margin = t["score"] - ms[1]["score"] if len(ms) > 1 else 1.0
    if t["score"] >= 0.9 and margin >= 0.2 and (not n or k / n >= 0.8):
        return {"level": 3, "label": LEVELS[3], "reason": "A very close match, clearly ahead of every other material."}
    return {"level": 2, "label": LEVELS[2], "reason": "All checks passed, but the match is not as close or as distinct as it could be."}


def checks(a):
    ms, snr = a["matches"], a["snr"]
    t = ms[0] if ms else None
    out = [{"id": "signal", "label": "The signal is clear",
            "passed": snr is not None and snr >= quality.MIN_SNR,
            "detail": ((f"Peaks stand more than 100× above the noise." if snr > 100 else
                        f"Peaks stand about {snr:.0f}× above the noise (at least {quality.MIN_SNR:g}× is needed).") if snr is not None
                       else "The noise level could not be measured.")}]
    if t:
        cov_ok = t["coverage"] >= quality.MIN_COVERAGE and t.get("sample_signal_in_overlap", 1) >= quality.MIN_SAMPLE_IN_OVERLAP
        out.append({"id": "range", "label": "Your measurement covers the reference", "passed": cov_ok,
                    "detail": f"{t['coverage'] * 100:.0f}% of the reference's range was measured."})
        out.append({"id": "close", "label": "The shapes match closely", "passed": t["score"] >= quality.MIN_SCORE,
                    "detail": f"Similarity {t['score']:.2f} out of 1 (at least {quality.MIN_SCORE:.2f} is needed)."})
        if len(ms) > 1:
            gap = t["score"] - ms[1]["score"]
            out.append({"id": "distinct", "label": "It clearly beats the next option", "passed": gap >= quality.MIN_MARGIN,
                        "detail": f"{gap:.2f} ahead of {ms[1]['name']} (at least {quality.MIN_MARGIN:.2f} is needed)."})
        k, n = _peak_fraction(t)
        if n:
            out.append({"id": "peaks", "label": "The key peaks line up", "passed": k / n >= quality.MIN_PEAK_FRACTION,
                        "detail": f"{k} of the reference's {n} peaks appear in your spectrum."})
        out.append({"id": "single", "label": "It looks like one material, not a mixture", "passed": not a.get("mixture"),
                    "detail": (f"A blend of {a['mixture']['names'][0]} and {a['mixture']['names'][1]} fits better."
                               if a.get("mixture") else "No pair of materials fits better than the best single one.")})
        out.append({"id": "measured", "label": "The reference is a real measurement", "passed": t.get("category") == "measured",
                    "detail": (f"From {t['source'].split(' ')[0]}." if t.get("category") == "measured"
                               else "A simulated demo reference.")})
    return out


def build(a, sections):
    sp = sections["spectrum"]["data"]
    ms = a["matches"]
    x, y = _down(sp["x"], sp["processed"])
    ov = {"x": x, "sample": _scaled(y), "reference": None, "reference_name": None, "peaks": []}
    curve = a.get("top_reference_curve")
    if curve and ms:
        ov.update(reference={"x": curve["x"], "y": _scaled(curve["y"])}, reference_name=curve["name"],
                  reference_category=ms[0].get("category"))
        heights = {round(p["position"], 3): p["relative_height"] for p in a["peaks"]}
        shared = [m["sample"] for m in ms[0]["peak_agreement"]["matched"]]
        ov["peaks"] = sorted(round(p) for p in sorted(shared, key=lambda p: -heights.get(round(p, 3), 0))[:6])
    if not ov["peaks"]:
        ov["peaks"] = sorted(round(p["position"]) for p in sorted(a["peaks"], key=lambda p: -p["relative_height"])[:5])
    ymax = max(ov["sample"]) if ov["sample"] else 1
    ov["peak_heights"] = [float(np.interp(p, x, ov["sample"])) if x else ymax for p in ov["peaks"]]
    cands = [{"name": m["name"], "score": max(0.0, round(m["score"], 3)), "category": m.get("category"),
              "top": i == 0} for i, m in enumerate(ms[:5])]
    return {"confidence": confidence(a), "overlay": ov,
            "candidates": {"items": cands, "threshold": quality.MIN_SCORE, "named": a["status"] == "ok"},
            "checks": checks(a)}
