#!/bin/bash
set -euo pipefail

export BHA_DATA_DIR="${BHA_DATA_DIR:-/app/beamalias}"
export BHA_AUDIT_DIR="${BHA_AUDIT_DIR:-/app/audit}"
mkdir -p "${BHA_AUDIT_DIR}"

python3 - <<'PY'
import json
import os
from pathlib import Path

def dump_pretty(path, obj):
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def solve_beam_hop(data_dir: Path, audit_dir: Path) -> None:
    policy = json.loads((data_dir / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    epochs = json.loads((data_dir / "epochs.json").read_text(encoding="utf-8"))
    frames_doc = json.loads((data_dir / "frames.json").read_text(encoding="utf-8"))
    locks_doc = json.loads((data_dir / "locks.json").read_text(encoding="utf-8"))

    window = int(policy["window_bins"])
    nyquist = float(policy["nyquist_hz"])
    hop_span = int(policy["hop_span"])
    vote_ratio = float(policy["vote_ratio"])
    current_epoch = int(epochs["current_epoch"])

    if manifest["cal_tag"] != manifest["run_tag"]:
        nyquist = nyquist * 0.5

    locks = locks_doc["locks"]

    def locked_freq(freq: float) -> float | None:
        for lk in locks:
            if float(lk["band_low"]) <= freq <= float(lk["band_high"]):
                return float(lk["lock_hz"])
        return None

    bins: dict[str, dict] = {}
    for path in sorted((data_dir / "bins").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        bins[row["bin_id"]] = row

    active = {bid for bid, row in bins.items() if int(row["epoch"]) >= current_epoch - 1}
    total_weight = sum(float(bins[b]["weight"]) for b in active)

    frames = sorted(
        frames_doc["frames"],
        key=lambda f: (int(f["frame"]), f["bin_id"]),
    )

    history: dict[str, list[float]] = {bid: [] for bid in bins}
    carry: dict[str, float] = {bid: 0.0 for bid in bins}

    alias_rows = []
    vote_rows = []
    window_rows = []
    bin_states = []

    alias_total = 0
    hop_carry_total = 0
    stale_skipped = 0
    vote_accepted = 0

    for fr in frames:
        frame = int(fr["frame"])
        bid = fr["bin_id"]
        freq = float(fr["freq_hz"])
        amp = float(fr["amplitude"])

        stale = bid not in active
        if stale:
            stale_skipped += 1

        hop_bonus = 0.0
        if frame % hop_span != 0 and carry[bid] > 0:
            hop_bonus = carry[bid]
            hop_carry_total += 1

        effective_amp = amp + hop_bonus
        carry[bid] = effective_amp * 0.5 if frame % hop_span == 0 else carry[bid]

        lk = locked_freq(freq)
        if lk is not None:
            report_freq = lk
            aliased = False
        elif freq > nyquist:
            report_freq = round(2 * nyquist - freq, 6)
            aliased = True
        else:
            report_freq = round(freq, 6)
            aliased = False

        hist = history[bid]
        hist.append(report_freq)
        if len(hist) > window:
            hist.pop(0)
        window_mean = sum(hist) / len(hist)

        if not stale:
            alias_rows.append(
                {
                    "aliased": aliased,
                    "amplitude": round(effective_amp, 6),
                    "bin_id": bid,
                    "frame": frame,
                    "report_freq_hz": report_freq,
                }
            )
        if aliased and not stale:
            alias_total += 1

        bucket = f"{report_freq:.1f}"
        same_frame = [x for x in frames if int(x["frame"]) == frame]
        agree_weight = sum(
            float(bins[x["bin_id"]]["weight"])
            for x in same_frame
            if f"{(locked_freq(float(x['freq_hz'])) or (round(2 * nyquist - float(x['freq_hz']), 6) if float(x['freq_hz']) > nyquist else round(float(x['freq_hz']), 6))):.1f}" == bucket
            and x["bin_id"] in active
        )
        # recompute bucket per row for vote - use report_freq from each
        agree_weight = 0.0
        for x in same_frame:
            xf = float(x["freq_hz"])
            xlk = locked_freq(xf)
            if xlk is not None:
                xrf = xlk
            elif xf > nyquist:
                xrf = round(2 * nyquist - xf, 6)
            else:
                xrf = round(xf, 6)
            if f"{xrf:.1f}" == bucket and x["bin_id"] in active:
                agree_weight += float(bins[x["bin_id"]]["weight"])

        accepted_flag = (
            not stale and total_weight > 0 and agree_weight >= vote_ratio * total_weight
        )
        if accepted_flag:
            vote_accepted += 1

        vote_rows.append(
            {
                "accepted": accepted_flag,
                "agree_weight": round(agree_weight, 6),
                "bin_id": bid,
                "bucket": bucket,
                "frame": frame,
                "stale": stale,
            }
        )
        window_rows.append(
            {
                "bin_id": bid,
                "frame": frame,
                "hop_bonus": round(hop_bonus, 6),
                "window_mean_freq": round(window_mean, 6),
                "window_size": len(hist),
            }
        )

    for bid in sorted(bins):
        row = bins[bid]
        bin_states.append(
            {
                "bin_id": bid,
                "epoch": int(row["epoch"]),
                "stale": bid not in active,
                "weight": float(row["weight"]),
            }
        )

    summary = {
        "alias_total": alias_total,
        "current_epoch": current_epoch,
        "effective_nyquist_hz": round(nyquist, 6),
        "frame_total": len(frames),
        "hop_carry_total": hop_carry_total,
        "stale_skipped_total": stale_skipped,
        "vote_accepted_total": vote_accepted,
    }

    audit_dir.mkdir(parents=True, exist_ok=True)
    dump_pretty(audit_dir / "bin_states.json", {"bins": bin_states})
    dump_pretty(audit_dir / "alias_plan.json", {"entries": alias_rows})
    dump_pretty(audit_dir / "band_votes.json", {"votes": vote_rows})
    dump_pretty(audit_dir / "window_stats.json", {"windows": window_rows})
    dump_pretty(audit_dir / "summary.json", summary)




data_dir = Path(os.environ.get("BHA_DATA_DIR", "/app/beamalias"))
audit_dir = Path(os.environ.get("BHA_AUDIT_DIR", "/app/audit"))
solve_beam_hop(data_dir, audit_dir)
PY
