"""Oracle: compute layout_report.json ground truth."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

TYPES_DIR = Path(os.environ.get("ORACLE_TYPES_DIR", "/app/data/types"))
CFG_PATH = Path(os.environ.get("ORACLE_CONFIG", "/app/config/platform.json"))
OUT_PATH = Path(os.environ.get("ORACLE_OUT", "/app/output/layout_report.json"))

ARRAY_RE = re.compile(r"^\[(.+);\s*(\d+)\]$")
ALIGN_RE = re.compile(r"^align\((\d+)\)$")


def align_up(off: int, a: int) -> int:
    if a <= 1:
        return off
    m = off % a
    if m == 0:
        return off
    return off + (a - m)


def load_defs(types_dir: Path) -> dict[str, dict]:
    defs: dict[str, dict] = {}
    for p in sorted(types_dir.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        defs[d["id"]] = d
    return defs


def discriminant_layout(variant_count: int) -> tuple[int, int]:
    if variant_count <= 256:
        return 1, 1
    if variant_count <= 65536:
        return 2, 2
    return 4, 4


class LayoutOracle:
    def __init__(self, defs: dict[str, dict], primitives: dict[str, dict]):
        self.defs = defs
        self.primitives = primitives
        self.memo_ty: dict[str, tuple[int, int]] = {}

    def sa_string(self, ty: str, stack: frozenset[str]) -> tuple[int, int]:
        ty = ty.strip()
        if ty in self.primitives:
            p = self.primitives[ty]
            return int(p["size"]), int(p["align"])
        mm = ARRAY_RE.match(ty)
        if mm:
            inner = mm.group(1).strip()
            n = int(mm.group(2))
            bs, ba = self.sa_string(inner, stack)
            return bs * n, ba
        if ty in self.defs:
            return self.sa_id(ty, stack)
        raise KeyError(f"Unknown type: {ty!r}")

    def sa_id(self, tid: str, stack: frozenset[str]) -> tuple[int, int]:
        if tid in self.memo_ty:
            return self.memo_ty[tid]
        if tid in stack:
            raise RuntimeError(f"Recursive type dependency involving {tid!r}")

        stack2 = frozenset({tid, *stack})
        obj = self.defs[tid]
        if obj["kind"] == "struct":
            sz, al = self._layout_struct_sa(obj, stack2)
        else:
            sz, al = self._layout_enum_sa(obj, stack2)
        self.memo_ty[tid] = (sz, al)
        return sz, al

    def _natural_struct_align_declaration_order(self, fields: list[dict], stack: frozenset[str]) -> int:
        als: list[int] = []
        for f in fields:
            _, fa = self.sa_string(f["type"].strip(), stack)
            als.append(fa)
        return 1 if not als else max(als)

    def _layout_struct_ordered(
        self,
        pairs: list[tuple[str, str]],
        *,
        packed: bool,
        align_floor: int | None,
        stack: frozenset[str],
    ) -> tuple[list[dict], int, int, int, int]:
        reps: list[dict] = []
        resolved: list[tuple[str, int, int]] = []
        for name, ty in pairs:
            sz, fa = self.sa_string(ty, stack)
            resolved.append((name, sz, fa))

        if packed:
            off = 0
            for name, sz, fa in resolved:
                reps.append(
                    {
                        "name": name,
                        "offset": off,
                        "size": sz,
                        "alignment": fa,
                        "padding_before": 0,
                    }
                )
                off += sz
            return reps, off, 1, 0, 0

        natural_align = 1 if not resolved else max(fa for _, _, fa in resolved)
        struct_align = natural_align if align_floor is None else max(natural_align, align_floor, 1)

        off = 0
        pad_sum = 0
        for name, sz, fa in resolved:
            need = align_up(off, fa)
            pb = need - off
            pad_sum += pb
            off = need
            reps.append(
                {
                    "name": name,
                    "offset": off,
                    "size": sz,
                    "alignment": fa,
                    "padding_before": pb,
                }
            )
            off += sz

        raw_end = off
        final = align_up(raw_end, struct_align)
        trailing = final - raw_end
        return reps, final, struct_align, trailing, pad_sum + trailing

    def _rust_field_order(self, fields: list[dict], stack: frozenset[str]) -> list[tuple[str, str]]:
        triples: list[tuple[str, str, int, int]] = []
        for f in fields:
            name = f["name"]
            ty = f["type"].strip()
            sz, al = self.sa_string(ty, stack)
            triples.append((name, ty, sz, al))
        triples.sort(key=lambda x: (-x[3], -x[2], x[0]))
        return [(n, t) for n, t, _, __ in triples]

    def _layout_struct_sa(self, obj: dict, stack: frozenset[str]) -> tuple[int, int]:
        fields = obj.get("fields") or []
        repr_raw = obj["repr"].strip()

        if repr_raw.lower() == "packed":
            _, sz, al, _, _ = self._layout_struct_ordered(
                [(f["name"], f["type"].strip()) for f in fields],
                packed=True,
                align_floor=None,
                stack=stack,
            )
            return sz, al

        if repr_raw == "Rust":
            order = self._rust_field_order(fields, stack)
            _, sz, al, _, _ = self._layout_struct_ordered(
                order,
                packed=False,
                align_floor=None,
                stack=stack,
            )
            return sz, al

        m = ALIGN_RE.match(repr_raw.replace(" ", ""))
        if m:
            n = int(m.group(1))
            pairs = [(f["name"], f["type"].strip()) for f in fields]
            _, sz, struct_align, _, _ = self._layout_struct_ordered(
                pairs,
                packed=False,
                align_floor=n,
                stack=stack,
            )
            return sz, struct_align

        pairs = [(f["name"], f["type"].strip()) for f in fields]
        _, sz, struct_align, _, _ = self._layout_struct_ordered(
            pairs,
            packed=False,
            align_floor=None,
            stack=stack,
        )
        return sz, struct_align

    def _variant_payload_sa(self, v: dict, stack: frozenset[str]) -> tuple[int, int]:
        vfs = v.get("fields") or []
        if not vfs:
            return 0, 1
        pairs = [(ff["name"], ff["type"].strip()) for ff in vfs]
        _, psz, payload_align, _, _ = self._layout_struct_ordered(
            pairs,
            packed=False,
            align_floor=None,
            stack=stack,
        )
        return psz, payload_align

    def _layout_enum_sa(self, obj: dict, stack: frozenset[str]) -> tuple[int, int]:
        variants = obj.get("variants") or []
        repr_raw = obj["repr"].strip()
        vn = len(variants)

        if vn == 2 and repr_raw != "C":
            empty_exists = any(not (vv.get("fields") or []) for vv in variants)
            ptr_arm = False
            for vv in variants:
                fs = vv.get("fields") or []
                if len(fs) == 1:
                    tt = fs[0]["type"].strip()
                    if tt in ("pointer", "reference"):
                        ptr_arm = True
                        break
            if empty_exists and ptr_arm:
                p = self.primitives["pointer"]
                return int(p["size"]), int(p["align"])

        if repr_raw != "C":
            raise ValueError(f"Unsupported enum repr {repr_raw!r} on {obj.get('id')!r}")

        ds, da = discriminant_layout(vn)
        pay_infos = [self._variant_payload_sa(v, stack) for v in variants]
        max_pa = max((pi[1] for pi in pay_infos), default=1)
        max_ps = max((pi[0] for pi in pay_infos), default=0)

        union_start = align_up(ds, max_pa)
        raw_end = union_start + max_ps
        enum_align = max(da, max_pa)
        total = align_up(raw_end, enum_align)
        return total, enum_align


def main() -> None:
    defs = load_defs(TYPES_DIR)
    plat = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    prim = plat["primitives"]

    ora = LayoutOracle(defs, prim)

    emitted: list[dict] = []
    for tid in sorted(defs.keys()):
        obj = defs[tid]
        if obj["kind"] == "struct":
            emitted.append(emit_struct(ora, tid, obj))
        else:
            emitted.append(emit_enum(ora, tid, obj))

    total_types = len(emitted)
    total_size_sum = sum(t["size"] for t in emitted)
    total_pad_sum = sum(t["total_padding"] for t in emitted)
    ratio = round((total_pad_sum / total_size_sum), 6) if total_size_sum > 0 else 0.0
    zst_count = sum(1 for t in emitted if t.get("is_zst"))
    niche_count = sum(1 for t in emitted if t.get("niche_optimized"))
    max_align = max(t["alignment"] for t in emitted) if emitted else 0

    largest_id = ""
    largest_sz = -1
    for t in emitted:
        if t["size"] > largest_sz or (
            t["size"] == largest_sz and (largest_id == "" or t["id"] < largest_id)
        ):
            largest_id = t["id"]
            largest_sz = t["size"]

    most_pad_id = ""
    most_pad_v = -1
    for t in emitted:
        p = t["total_padding"]
        if p > most_pad_v or (p == most_pad_v and (most_pad_id == "" or t["id"] < most_pad_id)):
            most_pad_id = t["id"]
            most_pad_v = p

    payload = {
        "platform": plat.get("architecture", "x86_64"),
        "types": emitted,
        "summary": {
            "total_types": total_types,
            "total_size_all_types": total_size_sum,
            "total_padding_all_types": total_pad_sum,
            "padding_ratio": ratio,
            "zst_count": zst_count,
            "niche_optimized_count": niche_count,
            "max_alignment": max_align,
            "largest_type": largest_id,
            "most_padded_type": most_pad_id,
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def emit_struct(ora: LayoutOracle, tid: str, obj: dict) -> dict:
    fields = obj.get("fields") or []
    repr_raw = obj["repr"].strip()
    stack = frozenset({tid})

    if repr_raw.lower() == "packed":
        reps, sz, alignment, trailing, tp = ora._layout_struct_ordered(
            [(f["name"], f["type"].strip()) for f in fields],
            packed=True,
            align_floor=None,
            stack=stack,
        )
        fo = [f["name"] for f in fields]
        is_zst = sz == 0
        return struct_row(obj["id"], repr_raw, sz, alignment, is_zst, reps, trailing, tp, fo)

    if repr_raw == "Rust":
        order = ora._rust_field_order(fields, stack)
        reps, sz, alignment, trailing, tp = ora._layout_struct_ordered(
            order,
            packed=False,
            align_floor=None,
            stack=stack,
        )
        fo = [n for n, _ in order]
        is_zst = sz == 0
        return struct_row(obj["id"], repr_raw, sz, alignment, is_zst, reps, trailing, tp, fo)

    m = ALIGN_RE.match(repr_raw.replace(" ", ""))
    if m:
        n = int(m.group(1))
        pairs = [(f["name"], f["type"].strip()) for f in fields]
        reps, sz, alignment, trailing, tp = ora._layout_struct_ordered(
            pairs,
            packed=False,
            align_floor=n,
            stack=stack,
        )
        is_zst = sz == 0
        fo = [f["name"] for f in fields]
        return struct_row(obj["id"], repr_raw, sz, alignment, is_zst, reps, trailing, tp, fo)

    pairs = [(f["name"], f["type"].strip()) for f in fields]
    reps, sz, alignment, trailing, tp = ora._layout_struct_ordered(
        pairs,
        packed=False,
        align_floor=None,
        stack=stack,
    )
    is_zst = sz == 0
    fo = [f["name"] for f in fields]
    return struct_row(obj["id"], repr_raw, sz, alignment, is_zst, reps, trailing, tp, fo)


def struct_row(
    tid: str,
    repr_raw: str,
    sz: int,
    alignment: int,
    is_zst: bool,
    reps: list[dict],
    trailing: int,
    tp: int,
    field_order: list[str],
) -> dict:
    return {
        "id": tid,
        "kind": "struct",
        "repr": repr_raw,
        "size": sz,
        "alignment": alignment,
        "is_zst": is_zst,
        "niche_optimized": False,
        "fields": [] if is_zst else reps,
        "trailing_padding": trailing,
        "total_padding": tp,
        "field_order": field_order if not is_zst else [],
    }


def emit_enum(ora: LayoutOracle, tid: str, obj: dict) -> dict:
    repr_raw = obj["repr"].strip()
    variants = obj.get("variants") or []
    vn = len(variants)
    stack = frozenset({tid})

    if vn == 2 and repr_raw != "C":
        empty_exists = any(not (vv.get("fields") or []) for vv in variants)
        ptr_arm = False
        for vv in variants:
            fs = vv.get("fields") or []
            if len(fs) == 1:
                tt = fs[0]["type"].strip()
                if tt in ("pointer", "reference"):
                    ptr_arm = True
                    break
        if empty_exists and ptr_arm:
            vm = []
            for v in variants:
                if not (v.get("fields") or []):
                    vm.append({"name": v["name"], "payload_size": 0, "payload_alignment": 1})
                else:
                    ps, pa = ora._variant_payload_sa(v, stack)
                    vm.append({"name": v["name"], "payload_size": ps, "payload_alignment": pa})

            psz = int(ora.primitives["pointer"]["size"])
            pal = int(ora.primitives["pointer"]["align"])
            return {
                "id": tid,
                "kind": "enum",
                "repr": repr_raw,
                "size": psz,
                "alignment": pal,
                "is_zst": False,
                "niche_optimized": True,
                "discriminant": None,
                "variants": vm,
                "trailing_padding": 0,
                "total_padding": 0,
                "field_order": None,
            }

    ds, da = discriminant_layout(vn)
    vm = []
    pay_infos = []
    for v in variants:
        psz, pa = ora._variant_payload_sa(v, stack)
        vm.append({"name": v["name"], "payload_size": psz, "payload_alignment": pa})
        pay_infos.append((psz, pa))

    max_pa = max((pa for _, pa in pay_infos), default=1)
    max_ps = max((psz for psz, _ in pay_infos), default=0)

    union_start = align_up(ds, max_pa)
    disc_gap_pad = union_start - ds

    raw_end = union_start + max_ps
    enum_align = max(da, max_pa)
    total = align_up(raw_end, enum_align)
    trailing = total - raw_end

    return {
        "id": tid,
        "kind": "enum",
        "repr": repr_raw,
        "size": total,
        "alignment": enum_align,
        "is_zst": False,
        "niche_optimized": False,
        "discriminant": {"size": ds, "alignment": da},
        "variants": vm,
        "trailing_padding": trailing,
        "total_padding": disc_gap_pad,
        "field_order": None,
    }


main()

if __name__ == "__main__":
    raise SystemExit(0)
