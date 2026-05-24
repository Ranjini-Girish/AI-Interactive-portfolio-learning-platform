import json
import os
import pytest

REPORT_PATH = "/app/output/battle_report.json"

@pytest.fixture(scope="module")
def report():
    assert os.path.isfile(REPORT_PATH), f"Output file not found: {REPORT_PATH}"
    with open(REPORT_PATH) as f:
        data = json.load(f)
    return data

@pytest.fixture(scope="module")
def battles(report):
    return {b["battle_id"]: b for b in report["battles"]}

def bt(battles, bid):
    return battles[bid]

def get_round(battle, rnum):
    for r in battle["rounds"]:
        if r["round"] == rnum:
            return r
    return None

def get_turn(rnd, actor):
    for t in rnd["turns"]:
        if t["actor"] == actor:
            return t
    return None

# ── Structural ──

def test_output_file_exists():
    assert os.path.isfile(REPORT_PATH)

def test_valid_json():
    with open(REPORT_PATH) as f:
        data = json.load(f)
    assert isinstance(data, dict)

def test_top_level_keys(report):
    assert "battles" in report
    assert "summary" in report

def test_battle_count(report):
    assert len(report["battles"]) == 6

def test_battle_ids(report):
    ids = [b["battle_id"] for b in report["battles"]]
    assert ids == ["battle_01", "battle_02", "battle_03", "battle_04", "battle_05", "battle_06"]

def test_sorted_keys_top(report):
    assert list(report.keys()) == sorted(report.keys())

def test_sorted_keys_summary(report):
    assert list(report["summary"].keys()) == sorted(report["summary"].keys())

def test_sorted_keys_battle_stats(battles):
    for b in battles.values():
        assert list(b["stats"].keys()) == sorted(b["stats"].keys())

# ── Summary ──

def test_summary_total_battles(report):
    assert report["summary"]["total_battles"] == 6

def test_summary_hero_wins(report):
    assert report["summary"]["hero_wins"] == 5

def test_summary_enemy_wins(report):
    assert report["summary"]["enemy_wins"] == 1

def test_summary_total_rounds(report):
    assert report["summary"]["total_rounds"] == 29

def test_summary_longest_battle(report):
    assert report["summary"]["longest_battle_rounds"] == 9

def test_summary_shortest_battle(report):
    assert report["summary"]["shortest_battle_rounds"] == 2

def test_summary_total_crits(report):
    assert report["summary"]["total_critical_hits"] == 17

def test_summary_total_damage(report):
    assert report["summary"]["total_damage"] == 2614

def test_summary_total_status_ticks(report):
    assert report["summary"]["total_status_ticks"] == 27

# ── Battle 01: Basic combat + elemental advantage ──

def test_b01_winner(battles):
    assert bt(battles, "battle_01")["winner"] == "heroes"

def test_b01_total_rounds(battles):
    assert bt(battles, "battle_01")["total_rounds"] == 3

def test_b01_hero_damage(battles):
    assert bt(battles, "battle_01")["stats"]["hero_damage_dealt"] == 242

def test_b01_enemy_damage(battles):
    assert bt(battles, "battle_01")["stats"]["enemy_damage_dealt"] == 46

def test_b01_crits(battles):
    assert bt(battles, "battle_01")["stats"]["critical_hits"] == 1

def test_b01_shields(battles):
    assert bt(battles, "battle_01")["stats"]["shields_created"] == 1

def test_b01_survivors(battles):
    surv = {s["id"]: s["hp"] for s in bt(battles, "battle_01")["survivors"]}
    assert surv == {"aria": 154, "kai": 250}

def test_b01_r1_aria_damage_trap(battles):
    """Trap: fire vs nature = 1.5x. floor(45*120/100)=54, floor(12*0.6)=7, base=47, elem=floor(47*1.5)=70"""
    r1 = get_round(bt(battles, "battle_01"), 1)
    t = get_turn(r1, "aria")
    assert t["damage_per_target"] == [70]

def test_b01_r1_aria_targets_lowest_hp(battles):
    """goblin_b has 100 HP < goblin_a 120 HP, so aria targets goblin_b"""
    r1 = get_round(bt(battles, "battle_01"), 1)
    t = get_turn(r1, "aria")
    assert t["targets"] == ["goblin_b"]

def test_b01_r1_kai_crit(battles):
    r1 = get_round(bt(battles, "battle_01"), 1)
    t = get_turn(r1, "kai")
    assert t["critical_per_target"] == [True]
    assert t["damage_per_target"] == [42]

def test_b01_r1_goblin_b_dies(battles):
    r1 = get_round(bt(battles, "battle_01"), 1)
    assert "goblin_b" in r1["deaths_this_round"]

def test_b01_r3_aria_burn_damage_floor_trap(battles):
    """Trap: goblin_a with burn, eff_def=floor(15*0.8)=12, floor(12*0.6)=7.
    base=floor(45*120/100)-7=54-7=47, elem=floor(47*1.5)=floor(70.5)=70.
    Wrong: if model combines floors, gets different value."""
    r3 = get_round(bt(battles, "battle_01"), 3)
    t = get_turn(r3, "aria")
    assert t["damage_per_target"] == [67]

# ── Battle 02: Mutual light/dark weakness, 1v1 ──

def test_b02_winner(battles):
    assert bt(battles, "battle_02")["winner"] == "enemies"

def test_b02_total_rounds(battles):
    assert bt(battles, "battle_02")["total_rounds"] == 2

def test_b02_crits(battles):
    assert bt(battles, "battle_02")["stats"]["critical_hits"] == 2

def test_b02_hero_damage(battles):
    assert bt(battles, "battle_02")["stats"]["hero_damage_dealt"] == 155

def test_b02_enemy_damage(battles):
    assert bt(battles, "battle_02")["stats"]["enemy_damage_dealt"] == 186

def test_b02_survivors(battles):
    surv = {s["id"]: s["hp"] for s in bt(battles, "battle_02")["survivors"]}
    assert surv == {"wraith_a": 5}

def test_b02_r1_luna_smite_vs_dark(battles):
    """Light vs Dark = 1.5x. floor(50*130/100)=65, floor(14*0.6)=8, base=57, elem=floor(57*1.5)=85"""
    r1 = get_round(bt(battles, "battle_02"), 1)
    t = get_turn(r1, "luna")
    assert t["damage_per_target"] == [85]

def test_b02_r1_wraith_crit_dmg(battles):
    """Dark vs Light = 1.5x + crit 1.75x.
    floor(48*135/100)=64, floor(15*0.6)=9, base=55, elem=floor(55*1.5)=82, crit=floor(82*1.75)=143"""
    r1 = get_round(bt(battles, "battle_02"), 1)
    t = get_turn(r1, "wraith_a")
    assert t["critical_per_target"] == [True]
    assert t["damage_per_target"] == [143]

def test_b02_r2_luna_radiance_crit(battles):
    """AoE on single target, light vs dark 1.5x, with crit.
    floor(50*70/100)=35, floor(14*0.6)=8, base=27, elem=floor(27*1.5)=40, crit=floor(40*1.75)=70"""
    r2 = get_round(bt(battles, "battle_02"), 2)
    t = get_turn(r2, "luna")
    assert t["critical_per_target"] == [True]
    assert t["damage_per_target"] == [70]

# ── Battle 03: Shield absorb + burn defense reduction ──

def test_b03_winner(battles):
    assert bt(battles, "battle_03")["winner"] == "heroes"

def test_b03_total_rounds(battles):
    assert bt(battles, "battle_03")["total_rounds"] == 9

def test_b03_shields_created(battles):
    assert bt(battles, "battle_03")["stats"]["shields_created"] == 4

def test_b03_status_damage(battles):
    assert bt(battles, "battle_03")["stats"]["status_effect_damage"] == 96

def test_b03_crits(battles):
    assert bt(battles, "battle_03")["stats"]["critical_hits"] == 5

def test_b03_survivors(battles):
    surv = {s["id"]: s["hp"] for s in bt(battles, "battle_03")["survivors"]}
    assert surv == {"kai": 27}

def test_b03_r1_imp_a_vs_kai_burn_trap(battles):
    """Fire vs water = 0.75x. floor(38*105/100)=39, floor(35*0.6)=21, base=18, elem=floor(18*0.75)=13"""
    r1 = get_round(bt(battles, "battle_03"), 1)
    t = get_turn(r1, "imp_a")
    assert t["damage_per_target"] == [13]

def test_b03_r1_burn_tick(battles):
    """Kai has burn: tick = floor(250 * 0.05) = 12"""
    r1 = get_round(bt(battles, "battle_03"), 1)
    assert len(r1["status_ticks"]) == 1
    tick = r1["status_ticks"][0]
    assert tick["entity"] == "kai"
    assert tick["effect"] == "burn"
    assert tick["damage"] == 12
    assert tick["hp_after"] == 208

def test_b03_r2_imp_b_burn_defense_trap(battles):
    """Kai burned: eff_def=floor(35*0.8)=28, floor(28*0.6)=16.
    floor(38*105/100)=39, base=max(1,39-16)=23, wrong_base if no burn: 39-21=18.
    Elem: floor(23*0.75)=17. Wrong if no burn effect: floor(18*0.75)=13"""
    r2 = get_round(bt(battles, "battle_03"), 2)
    t = get_turn(r2, "imp_a")
    assert t["damage_per_target"] == [17], "Burn defense reduction not applied"

def test_b03_r3_shield_absorb_trap(battles):
    """Kai has shield from round 2 (defense*1.5 = floor(35*1.5) = 52).
    Round 3, imp_a hits with 17 damage. Shield absorbs, so Kai HP stays at 150.
    imp_b also hits with 17. Shield absorbs again (52-17=35 remaining). Kai HP stays."""
    r3 = get_round(bt(battles, "battle_03"), 3)
    t_a = get_turn(r3, "imp_a")
    assert t_a["hp_after"]["kai"] == 150
    t_b = get_turn(r3, "imp_b")
    assert t_b["hp_after"]["kai"] == 150

def test_b03_r3_kai_crit(battles):
    """Kai crits imp_a: water vs fire 1.5x. floor(35*110/100)=38, floor(10*0.6)=6, base=32.
    elem=floor(32*1.5)=48, crit=floor(48*1.75)=84"""
    r3 = get_round(bt(battles, "battle_03"), 3)
    t = get_turn(r3, "kai")
    assert t["critical_per_target"] == [True]
    assert t["damage_per_target"] == [84]

# ── Battle 04: Stun + poison + burn ──

def test_b04_winner(battles):
    assert bt(battles, "battle_04")["winner"] == "heroes"

def test_b04_total_rounds(battles):
    assert bt(battles, "battle_04")["total_rounds"] == 6

def test_b04_stuns(battles):
    assert bt(battles, "battle_04")["stats"]["stuns_applied"] == 3

def test_b04_status_damage(battles):
    assert bt(battles, "battle_04")["stats"]["status_effect_damage"] == 198

def test_b04_survivors(battles):
    surv = {s["id"]: s["hp"] for s in bt(battles, "battle_04")["survivors"]}
    assert surv == {"aria": 53, "rex": 280}

def test_b04_r1_burn_and_poison_ticks(battles):
    """Golem has burn AND poison. Burn ticks first (alphabetical): floor(320*0.05)=16.
    Poison ticks second: floor(320*0.08)=25."""
    r1 = get_round(bt(battles, "battle_04"), 1)
    ticks = r1["status_ticks"]
    assert len(ticks) == 2
    assert ticks[0]["effect"] == "burn"
    assert ticks[0]["damage"] == 16
    assert ticks[0]["hp_after"] == 252
    assert ticks[1]["effect"] == "poison"
    assert ticks[1]["damage"] == 25
    assert ticks[1]["hp_after"] == 227

def test_b04_r2_aoe_stun_trap(battles):
    """Frost nova is AoE stun. Applies stun to first alive target (aria).
    AoE does full damage to each target (NOT split)."""
    r2 = get_round(bt(battles, "battle_04"), 2)
    t = get_turn(r2, "golem_a")
    assert t["targets"] == ["aria", "rex"]
    assert t["effects_applied"] == ["stun"]

def test_b04_r3_stun_skip_turn(battles):
    """Aria is stunned in round 3 - should skip turn."""
    r3 = get_round(bt(battles, "battle_04"), 3)
    t = get_turn(r3, "aria")
    assert t["skill"] == "stunned"
    assert t["targets"] == []
    assert t["damage_per_target"] == []

def test_b04_r3_status_tick_order(battles):
    """Burn and poison ticks alphabetically. Burn first, poison second."""
    r3 = get_round(bt(battles, "battle_04"), 3)
    ticks = r3["status_ticks"]
    assert len(ticks) == 2
    assert ticks[0]["effect"] == "burn"
    assert ticks[1]["effect"] == "poison"

def test_b04_r5_vine_lash_burn_defense_trap(battles):
    """Rex vine_lash vs burned golem. Golem burned: eff_def=floor(42*0.8)=33.
    floor(33*0.6)=19, floor(40*100/100)=40, base=max(1,40-19)=21.
    Nature vs water = 1.5x. elem=floor(21*1.5)=floor(31.5)=31.
    Wrong without burn: floor(42*0.6)=25, base=40-25=15, elem=floor(15*1.5)=22"""
    r5 = get_round(bt(battles, "battle_04"), 5)
    t = get_turn(r5, "rex")
    assert t["damage_per_target"] == [22], "Expected 22 from vine_lash on round 5"

def test_b04_r6_poison_kills_golem(battles):
    """Golem dies from poison tick at end of round 6."""
    r6 = get_round(bt(battles, "battle_04"), 6)
    ticks = r6["status_ticks"]
    assert any(t["entity"] == "golem_a" and t["hp_after"] == 0 for t in ticks)
    assert "golem_a" in r6["deaths_this_round"]

# ── Battle 05: AoE full damage ──

def test_b05_winner(battles):
    assert bt(battles, "battle_05")["winner"] == "heroes"

def test_b05_total_rounds(battles):
    assert bt(battles, "battle_05")["total_rounds"] == 5

def test_b05_hero_damage(battles):
    assert bt(battles, "battle_05")["stats"]["hero_damage_dealt"] == 359

def test_b05_crits(battles):
    assert bt(battles, "battle_05")["stats"]["critical_hits"] == 4

def test_b05_survivors(battles):
    surv = {s["id"]: s["hp"] for s in bt(battles, "battle_05")["survivors"]}
    assert surv == {"luna": 28, "rex": 280}

def test_b05_r1_luna_kills_goblin_d(battles):
    """Luna holy_smite targets goblin_d (lowest HP=90). Light vs nature = 1.0x.
    Crit: floor(50*130/100)=65, floor(10*0.6)=6, base=59, elem=59, crit=floor(59*1.75)=103"""
    r1 = get_round(bt(battles, "battle_05"), 1)
    t = get_turn(r1, "luna")
    assert t["targets"] == ["goblin_d"]
    assert t["critical_per_target"] == [True]
    assert t["damage_per_target"] == [103]

def test_b05_r2_aoe_full_damage_trap(battles):
    """Luna radiance AoE hits goblin_c and goblin_e. Each takes FULL damage, not split.
    Light vs nature = 1.0x. floor(50*70/100)=35.
    goblin_c: floor(15*0.6)=9, base=26, elem=26.
    goblin_e: floor(22*0.6)=13, base=22, elem=22."""
    r2 = get_round(bt(battles, "battle_05"), 2)
    t = get_turn(r2, "luna")
    assert t["targets"] == ["goblin_c", "goblin_e"]
    assert t["damage_per_target"] == [26, 22]

def test_b05_r1_poison_tick(battles):
    """goblin_c has poison: floor(120*0.08) = 9"""
    r1 = get_round(bt(battles, "battle_05"), 1)
    ticks = r1["status_ticks"]
    assert len(ticks) == 1
    assert ticks[0]["entity"] == "goblin_c"
    assert ticks[0]["damage"] == 9

# ── Battle 06: Boss fight, AoE burn from enemy ──

def test_b06_winner(battles):
    assert bt(battles, "battle_06")["winner"] == "heroes"

def test_b06_total_rounds(battles):
    assert bt(battles, "battle_06")["total_rounds"] == 4

def test_b06_hero_damage(battles):
    assert bt(battles, "battle_06")["stats"]["hero_damage_dealt"] == 393

def test_b06_enemy_damage(battles):
    assert bt(battles, "battle_06")["stats"]["enemy_damage_dealt"] == 247

def test_b06_status_damage(battles):
    assert bt(battles, "battle_06")["stats"]["status_effect_damage"] == 96

def test_b06_survivors(battles):
    surv = {s["id"]: s["hp"] for s in bt(battles, "battle_06")["survivors"]}
    assert surv == {"aria": 98, "kai": 221, "luna": 55}

def test_b06_r1_dragon_breath_aoe_burn_trap(battles):
    """Drake dragon_breath is AoE fire. Hits aria(fire), kai(water), luna(light).
    Fire vs fire = 1.0x, fire vs water = 0.75x, fire vs light = 1.0x.
    base for aria: floor(52*85/100)=44, floor(20*0.6)=12, base=32, elem=floor(32*1.0)=32
    base for kai: floor(52*85/100)=44, floor(35*0.6)=21, base=23, elem=floor(23*0.75)=17... but kai crits
    base for luna: floor(52*85/100)=44, floor(15*0.6)=9, base=35, elem=floor(35*1.0)=35"""
    r1 = get_round(bt(battles, "battle_06"), 1)
    t = get_turn(r1, "drake_a")
    assert t["targets"] == ["aria", "kai", "luna"]
    assert t["damage_per_target"] == [32, 29, 35]

def test_b06_r1_drake_kai_crit(battles):
    """Kai takes crit from drake AoE: elem=17, crit=floor(17*1.75)=29"""
    r1 = get_round(bt(battles, "battle_06"), 1)
    t = get_turn(r1, "drake_a")
    assert t["critical_per_target"] == [False, True, False]

def test_b06_r1_burn_ticks_both_sides(battles):
    """Both aria and drake have burn. Burns tick alphabetically by entity? No, by allEntities order.
    Aria burn: floor(200*0.05)=10. Drake burn: floor(450*0.05)=22."""
    r1 = get_round(bt(battles, "battle_06"), 1)
    ticks = r1["status_ticks"]
    assert len(ticks) == 2
    burn_aria = [t for t in ticks if t["entity"] == "aria"]
    burn_drake = [t for t in ticks if t["entity"] == "drake_a"]
    assert len(burn_aria) == 1
    assert burn_aria[0]["damage"] == 10
    assert len(burn_drake) == 1
    assert burn_drake[0]["damage"] == 22

def test_b06_r3_luna_crit_smite(battles):
    """Luna holy_smite on burned drake. eff_def=floor(28*0.8)=22, floor(22*0.6)=13.
    floor(50*130/100)=65, base=52, elem=floor(52*1.0)=52, crit=floor(52*1.75)=91"""
    r3 = get_round(bt(battles, "battle_06"), 3)
    t = get_turn(r3, "luna")
    assert t["critical_per_target"] == [True]
    assert t["damage_per_target"] == [91]

def test_b06_r3_kai_shield_absorb(battles):
    """Kai has shield from round 2 (floor(35*1.5)=52). Drake flame_roar AoE.
    Kai would take floor(21*1.0)=21 from neutral. Shield absorbs: 52-21=31 remaining. kai HP stays at 221."""
    r3 = get_round(bt(battles, "battle_06"), 3)
    t = get_turn(r3, "drake_a")
    assert t["hp_after"]["kai"] == 221

def test_b06_r2_aria_fire_ball_crit_trap(battles):
    """Aria fire_ball vs burned drake. Fire vs fire = 1.0x. Drake eff_def=floor(28*0.8)=22.
    floor(45*80/100)=36, floor(22*0.6)=13, base=23, elem=23, crit=floor(23*1.75)=40"""
    r2 = get_round(bt(battles, "battle_06"), 2)
    t = get_turn(r2, "aria")
    assert t["critical_per_target"] == [True]
    assert t["damage_per_target"] == [40]

# ── Cross-battle consistency checks ──

def test_total_damage_sum(report, battles):
    """Sum of all hero + enemy damage should match summary."""
    total = sum(b["stats"]["hero_damage_dealt"] + b["stats"]["enemy_damage_dealt"] for b in battles.values())
    assert total == report["summary"]["total_damage"]

def test_total_crits_sum(report, battles):
    total = sum(b["stats"]["critical_hits"] for b in battles.values())
    assert total == report["summary"]["total_critical_hits"]

def test_total_rounds_sum(report, battles):
    total = sum(b["total_rounds"] for b in battles.values())
    assert total == report["summary"]["total_rounds"]

def test_winner_counts(report, battles):
    hw = sum(1 for b in battles.values() if b["winner"] == "heroes")
    ew = sum(1 for b in battles.values() if b["winner"] == "enemies")
    assert hw == report["summary"]["hero_wins"]
    assert ew == report["summary"]["enemy_wins"]

# ── PRNG determinism check ──

def test_b01_prng_sequence_deterministic(battles):
    """The crit pattern in battle_01 must be exactly: no, no, no, yes, no, no, no, no, no"""
    b = bt(battles, "battle_01")
    all_crits = []
    for r in b["rounds"]:
        for t in r["turns"]:
            all_crits.extend(t["critical_per_target"])
    assert all_crits.count(True) == 1

def test_b02_prng_sequence_deterministic(battles):
    """Battle_02 with seed 137 should produce exactly 2 crits"""
    b = bt(battles, "battle_02")
    all_crits = []
    for r in b["rounds"]:
        for t in r["turns"]:
            all_crits.extend(t["critical_per_target"])
    assert all_crits.count(True) == 2

# ── JSON format checks ──

def test_json_trailing_newline():
    with open(REPORT_PATH, "rb") as f:
        content = f.read()
    assert content.endswith(b"\n")

def test_json_2_space_indent():
    with open(REPORT_PATH) as f:
        content = f.read()
    assert '  "battles"' in content

def test_survivors_sorted_by_id(battles):
    for b in battles.values():
        ids = [s["id"] for s in b["survivors"]]
        assert ids == sorted(ids), f"Survivors not sorted in {b['battle_id']}"

def test_deaths_sorted(battles):
    for b in battles.values():
        for r in b["rounds"]:
            deaths = r["deaths_this_round"]
            assert deaths == sorted(deaths), f"Deaths not sorted in {b['battle_id']} round {r['round']}"
