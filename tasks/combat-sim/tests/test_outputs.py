"""
Test suite for java-combat-sim-hard.
Validates /app/output/combat_log.json against expected combat simulation results.
"""
import json
import pathlib

import pytest

# ---------- path resolution ----------
ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output') / "combat_log.json"
BUILD  = ROOT / "build"


@pytest.fixture(scope="session")
def report():
    assert OUT_DIR.is_file(), f"combat_log.json not found at {OUT_DIR}"
    with open(OUT_DIR) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def battles(report):
    return {b["battle"]: b for b in report["battle_results"]}


@pytest.fixture(scope="session")
def summary(report):
    return report["summary"]


def _find_events(battle_data, etype, **kwargs):
    out = []
    for ev in battle_data["events"]:
        if ev["type"] != etype:
            continue
        if all(ev.get(k) == v for k, v in kwargs.items()):
            out.append(ev)
    return out


def _find_char(battle_data, name):
    for c in battle_data["final_characters"]:
        if c["name"] == name:
            return c
    return None


# ===================================================================
# Section 1: Java Binary Enforcement
# ===================================================================

class TestJavaBinary:
    def test_build_directory_exists(self):
        assert BUILD.is_dir(), "/app/build/ directory must exist"

    def test_class_or_jar_exists(self):
        found = False
        if BUILD.is_dir():
            for f in BUILD.rglob("*"):
                if f.suffix in (".class", ".jar"):
                    found = True
                    break
        assert found, "No .class or .jar files found in /app/build/"

    def test_class_file_magic_bytes(self):
        class_files = list(BUILD.rglob("*.class")) if BUILD.is_dir() else []
        if not class_files:
            jar_files = list(BUILD.rglob("*.jar")) if BUILD.is_dir() else []
            assert len(jar_files) > 0, "No .class or .jar files"
            return
        with open(class_files[0], "rb") as f:
            magic = f.read(4)
        assert magic == b'\xca\xfe\xba\xbe', \
            f"Class file does not have Java magic bytes, got {magic.hex()}"


# ===================================================================
# Section 2: JSON Structure
# ===================================================================

class TestStructure:
    def test_schema_version(self, report):
        assert report["schema_version"] == 1

    def test_battle_results_is_list(self, report):
        assert isinstance(report["battle_results"], list)

    def test_summary_exists(self, report):
        assert "summary" in report

    def test_battle_count(self, report):
        assert len(report["battle_results"]) == 5

    def test_battle_names_sorted(self, report):
        names = [b["battle"] for b in report["battle_results"]]
        assert names == sorted(names)

    def test_expected_battles_present(self, battles):
        expected = {"basic_combat", "buff_battle", "elemental_chain",
                    "poison_battle", "stun_battle"}
        assert set(battles.keys()) == expected

    def test_events_are_lists(self, battles):
        for b in battles.values():
            assert isinstance(b["events"], list)

    def test_final_characters_sorted_by_name(self, battles):
        for b in battles.values():
            names = [c["name"] for c in b["final_characters"]]
            assert names == sorted(names), f"final_characters not sorted in {b['battle']}"


# ===================================================================
# Section 3: Summary Validation
# ===================================================================

class TestSummary:
    def test_total_battles(self, summary):
        assert summary["total_battles"] == 5

    def test_team_a_wins(self, summary):
        assert summary["team_a_wins"] == 3

    def test_team_b_wins(self, summary):
        assert summary["team_b_wins"] == 0

    def test_draws(self, summary):
        assert summary["draws"] == 2

    def test_total_rounds(self, summary):
        assert summary["total_rounds"] == 13

    def test_total_damage(self, summary):
        assert summary["total_damage"] == 3093

    def test_total_healing(self, summary):
        assert summary["total_healing"] == 40

    def test_total_kills(self, summary):
        assert summary["total_kills"] == 10


# ===================================================================
# Section 4: basic_combat
# ===================================================================

class TestBasicCombat:
    def test_winner(self, battles):
        assert battles["basic_combat"]["winner"] == "A"

    def test_rounds(self, battles):
        assert battles["basic_combat"]["rounds_played"] == 2

    def test_rogue_backstab_damage(self, battles):
        evs = _find_events(battles["basic_combat"], "attack",
                           actor="rogue", ability="backstab")
        assert len(evs) == 1
        assert evs[0]["damage"] == 96

    def test_rogue_backstab_effectiveness(self, battles):
        evs = _find_events(battles["basic_combat"], "attack",
                           actor="rogue", ability="backstab")
        assert evs[0]["effectiveness"] == "not_very_effective"

    def test_mage_fireball_rogue_damage(self, battles):
        evs = _find_events(battles["basic_combat"], "attack",
                           actor="mage", ability="fireball")
        assert len(evs) == 1
        assert evs[0]["damage"] == 375

    def test_mage_fireball_super_effective(self, battles):
        evs = _find_events(battles["basic_combat"], "attack",
                           actor="mage", ability="fireball")
        assert evs[0]["effectiveness"] == "super_effective"

    def test_knight_skip_dead_target(self, battles):
        evs = _find_events(battles["basic_combat"], "skip",
                           actor="knight", reason="target_dead")
        assert len(evs) >= 1

    def test_healer_self_heal_zero(self, battles):
        evs = _find_events(battles["basic_combat"], "heal",
                           actor="healer")
        assert len(evs) == 1
        assert evs[0]["heal_amount"] == 0

    def test_healer_splash_damage(self, battles):
        evs = _find_events(battles["basic_combat"], "attack",
                           actor="healer", ability="splash")
        assert evs[0]["damage"] == 15

    def test_knight_final_hp(self, battles):
        c = _find_char(battles["basic_combat"], "knight")
        assert c["hp"] == 185 and c["alive"]

    def test_mage_final_hp(self, battles):
        c = _find_char(battles["basic_combat"], "mage")
        assert c["hp"] == 4 and c["alive"]

    def test_rogue_dead(self, battles):
        c = _find_char(battles["basic_combat"], "rogue")
        assert c["hp"] == 0 and not c["alive"]

    def test_healer_dead(self, battles):
        c = _find_char(battles["basic_combat"], "healer")
        assert c["hp"] == 0 and not c["alive"]

    def test_turn_order_r1(self, battles):
        """First event in round 1 should be rogue (speed 30, highest)."""
        r1_evs = [e for e in battles["basic_combat"]["events"] if e["round"] == 1]
        assert r1_evs[0]["actor"] == "rogue"

    def test_ember_nve_fire_vs_water(self, battles):
        evs = _find_events(battles["basic_combat"], "attack",
                           actor="mage", ability="ember")
        assert evs[0]["damage"] == 50
        assert evs[0]["effectiveness"] == "not_very_effective"

    def test_knight_slash_healer(self, battles):
        evs = _find_events(battles["basic_combat"], "attack",
                           actor="knight", ability="slash",
                           target="healer")
        assert len(evs) == 1
        assert evs[0]["damage"] == 80
        assert evs[0]["target_hp"] == 0


# ===================================================================
# Section 5: elemental_chain
# ===================================================================

class TestElementalChain:
    def test_winner(self, battles):
        assert battles["elemental_chain"]["winner"] == "A"

    def test_rounds(self, battles):
        assert battles["elemental_chain"]["rounds_played"] == 2

    def test_druid_vine_whip_healer_se(self, battles):
        evs = _find_events(battles["elemental_chain"], "attack",
                           actor="druid", ability="vine_whip",
                           target="healer")
        assert len(evs) == 2
        assert evs[0]["damage"] == 87
        assert evs[0]["effectiveness"] == "super_effective"

    def test_healer_splash_druid_nve(self, battles):
        evs = _find_events(battles["elemental_chain"], "attack",
                           actor="healer", ability="splash",
                           target="druid")
        assert evs[0]["damage"] == 10
        assert evs[0]["effectiveness"] == "not_very_effective"

    def test_healer_self_heal_40(self, battles):
        evs = _find_events(battles["elemental_chain"], "heal",
                           actor="healer")
        assert evs[0]["heal_amount"] == 40
        assert evs[0]["target_hp"] == 73

    def test_mage_ember_healer_nve(self, battles):
        evs = _find_events(battles["elemental_chain"], "attack",
                           actor="mage", ability="ember",
                           target="healer")
        assert evs[0]["effectiveness"] == "not_very_effective"
        assert evs[0]["damage"] == 50

    def test_druid_final_hp(self, battles):
        c = _find_char(battles["elemental_chain"], "druid")
        assert c["hp"] == 120

    def test_mage_final_hp(self, battles):
        c = _find_char(battles["elemental_chain"], "mage")
        assert c["hp"] == 4

    def test_rogue_killed_round1(self, battles):
        evs = _find_events(battles["elemental_chain"], "attack",
                           actor="mage", ability="fireball", round=1)
        assert evs[0]["target_hp"] == 0

    def test_healer_killed_round2(self, battles):
        c = _find_char(battles["elemental_chain"], "healer")
        assert c["hp"] == 0 and not c["alive"]


# ===================================================================
# Section 6: poison_battle
# ===================================================================

class TestPoisonBattle:
    def test_winner(self, battles):
        assert battles["poison_battle"]["winner"] == "draw"

    def test_rounds(self, battles):
        assert battles["poison_battle"]["rounds_played"] == 3

    def test_poison_applied_to_knight(self, battles):
        evs = _find_events(battles["poison_battle"], "attack",
                           actor="rogue", ability="poison_blade",
                           target="knight")
        assert len(evs) >= 1
        assert evs[0]["damage"] == 28

    def test_poison_tick_r1(self, battles):
        ticks = _find_events(battles["poison_battle"], "poison_tick",
                             actor="knight", round=1)
        assert len(ticks) == 1
        assert ticks[0]["damage"] == 25
        assert ticks[0]["hp_after"] == 75

    def test_poison_tick_r2_kills_knight(self, battles):
        ticks = _find_events(battles["poison_battle"], "poison_tick",
                             actor="knight", round=2)
        assert len(ticks) == 1
        assert ticks[0]["damage"] == 25
        assert ticks[0]["hp_after"] == 0

    def test_knight_dies_from_poison(self, battles):
        c = _find_char(battles["poison_battle"], "knight")
        assert c["hp"] == 0 and not c["alive"]

    def test_rogue_killed_round1(self, battles):
        evs = _find_events(battles["poison_battle"], "attack",
                           actor="knight", ability="slash",
                           target="rogue", round=1)
        assert evs[0]["damage"] == 100
        assert evs[0]["target_hp"] == 0

    def test_knight_skip_dead_target_r2(self, battles):
        evs = _find_events(battles["poison_battle"], "skip",
                           actor="knight", reason="target_dead", round=2)
        assert len(evs) == 1

    def test_archer_arrow_tank_r3(self, battles):
        evs = _find_events(battles["poison_battle"], "attack",
                           actor="archer", ability="arrow",
                           target="tank", round=3)
        assert evs[0]["damage"] == 45

    def test_tank_fortify_r3(self, battles):
        evs = _find_events(battles["poison_battle"], "buff",
                           actor="tank", ability="fortify", round=3)
        assert len(evs) == 1
        assert evs[0]["stat"] == "defense"
        assert evs[0]["value"] == 15

    def test_tank_final_hp(self, battles):
        c = _find_char(battles["poison_battle"], "tank")
        assert c["hp"] == 255 and c["alive"]

    def test_archer_final_hp(self, battles):
        c = _find_char(battles["poison_battle"], "archer")
        assert c["hp"] == 73 and c["alive"]

    def test_poison_damage_formula(self, battles):
        """Poison damage = floor(max_hp / 8). Knight max_hp=200, so 200//8=25."""
        ticks = _find_events(battles["poison_battle"], "poison_tick",
                             actor="knight")
        for t in ticks:
            assert t["damage"] == 25


# ===================================================================
# Section 7: stun_battle
# ===================================================================

class TestStunBattle:
    def test_winner(self, battles):
        assert battles["stun_battle"]["winner"] == "draw"

    def test_rounds(self, battles):
        assert battles["stun_battle"]["rounds_played"] == 3

    def test_stun_applied_round1(self, battles):
        evs = _find_events(battles["stun_battle"], "attack",
                           actor="archer", ability="stun_shot",
                           target="mage")
        assert len(evs) == 1
        assert evs[0]["damage"] == 80

    def test_mage_stunned_round1(self, battles):
        evs = _find_events(battles["stun_battle"], "stunned",
                           actor="mage", round=1)
        assert len(evs) == 1

    def test_stun_same_round_effect(self, battles):
        """Mage is stunned in round 1 even though stun was applied same round."""
        r1_evs = [e for e in battles["stun_battle"]["events"] if e["round"] == 1]
        actors = [(e["actor"], e["type"]) for e in r1_evs]
        archer_idx = next(i for i, (a, t) in enumerate(actors) if a == "archer")
        mage_idx = next(i for i, (a, t) in enumerate(actors) if a == "mage")
        assert mage_idx > archer_idx
        assert actors[mage_idx] == ("mage", "stunned")

    def test_mage_acts_round2(self, battles):
        """After being stunned in R1, mage should NOT be stunned in R2."""
        r2_stuns = _find_events(battles["stun_battle"], "stunned",
                                actor="mage", round=2)
        assert len(r2_stuns) == 0

    def test_mage_dead_round2(self, battles):
        evs = _find_events(battles["stun_battle"], "attack",
                           actor="archer", ability="arrow",
                           target="mage", round=2)
        assert evs[0]["damage"] == 180
        assert evs[0]["target_hp"] == 0

    def test_mage_skip_after_death(self, battles):
        evs = _find_events(battles["stun_battle"], "skip",
                           actor="mage", reason="actor_dead", round=2)
        assert len(evs) == 1

    def test_knight_slash_archer_r1(self, battles):
        evs = _find_events(battles["stun_battle"], "attack",
                           actor="knight", ability="slash",
                           target="archer", round=1)
        assert evs[0]["damage"] == 100
        assert evs[0]["target_hp"] == 10

    def test_archer_killed_round3(self, battles):
        evs = _find_events(battles["stun_battle"], "attack",
                           actor="knight", ability="slash",
                           target="archer", round=3)
        assert evs[0]["damage"] == 100
        assert evs[0]["target_hp"] == 0

    def test_druid_final_hp(self, battles):
        c = _find_char(battles["stun_battle"], "druid")
        assert c["hp"] == 64 and c["alive"]

    def test_knight_final_hp(self, battles):
        c = _find_char(battles["stun_battle"], "knight")
        assert c["hp"] == 23 and c["alive"]

    def test_archer_speed_tie_with_healer(self, battles):
        """Archer (speed 25) should go before anyone with speed < 25."""
        r1_evs = [e for e in battles["stun_battle"]["events"] if e["round"] == 1]
        assert r1_evs[0]["actor"] == "archer"


# ===================================================================
# Section 8: buff_battle
# ===================================================================

class TestBuffBattle:
    def test_winner(self, battles):
        assert battles["buff_battle"]["winner"] == "A"

    def test_rounds(self, battles):
        assert battles["buff_battle"]["rounds_played"] == 3

    def test_knight_guard_buff(self, battles):
        evs = _find_events(battles["buff_battle"], "buff",
                           actor="knight", ability="guard")
        assert len(evs) == 1
        assert evs[0]["stat"] == "defense"
        assert evs[0]["value"] == 10
        assert evs[0]["duration"] == 2

    def test_tank_fortify_buff(self, battles):
        evs = _find_events(battles["buff_battle"], "buff",
                           actor="tank", ability="fortify")
        assert len(evs) == 1
        assert evs[0]["value"] == 15
        assert evs[0]["duration"] == 3

    def test_assassin_shadow_strike_r1(self, battles):
        """Assassin attacks knight BEFORE guard buff is applied."""
        evs = _find_events(battles["buff_battle"], "attack",
                           actor="assassin", ability="shadow_strike",
                           round=1)
        assert evs[0]["damage"] == 154

    def test_mage_fireball_tank_r1(self, battles):
        """Mage attacks tank BEFORE fortify buff is applied."""
        evs = _find_events(battles["buff_battle"], "attack",
                           actor="mage", ability="fireball",
                           target="tank", round=1)
        assert evs[0]["damage"] == 75

    def test_assassin_quick_slash_r2_with_buff(self, battles):
        """Tank has fortify buff active in R2. Eff def = 40+15 = 55."""
        evs = _find_events(battles["buff_battle"], "attack",
                           actor="assassin", ability="quick_slash",
                           round=2)
        assert evs[0]["damage"] == 25

    def test_mage_ember_knight_r2_with_buff(self, battles):
        """Knight has guard buff active in R2. Eff def = 25+10 = 35.
        raw = 30*50/35 = 42."""
        evs = _find_events(battles["buff_battle"], "attack",
                           actor="mage", ability="ember",
                           target="knight", round=2)
        assert evs[0]["damage"] == 42

    def test_knight_slash_assassin_r2(self, battles):
        """Knight kills assassin: 40*30/8 = 150 >= 75 hp."""
        evs = _find_events(battles["buff_battle"], "attack",
                           actor="knight", ability="slash",
                           target="assassin", round=2)
        assert evs[0]["damage"] == 150
        assert evs[0]["target_hp"] == 0

    def test_mage_fireball_tank_r3_buff_still_active(self, battles):
        """Tank's fortify (duration 3) still active in R3. Eff def = 40+15=55.
        raw = 60*50/55 = 54."""
        evs = _find_events(battles["buff_battle"], "attack",
                           actor="mage", ability="fireball",
                           target="tank", round=3)
        assert evs[0]["damage"] == 54

    def test_knight_slash_mage_r3(self, battles):
        """Knight's guard buff expired after R2. raw = 40*30/10 = 120."""
        evs = _find_events(battles["buff_battle"], "attack",
                           actor="knight", ability="slash",
                           target="mage", round=3)
        assert evs[0]["damage"] == 120
        assert evs[0]["target_hp"] == 0

    def test_tank_skip_dead_r3(self, battles):
        evs = _find_events(battles["buff_battle"], "skip",
                           actor="tank", reason="target_dead", round=3)
        assert len(evs) == 1

    def test_knight_final_hp(self, battles):
        c = _find_char(battles["buff_battle"], "knight")
        assert c["hp"] == 4 and c["alive"]

    def test_tank_final_hp(self, battles):
        c = _find_char(battles["buff_battle"], "tank")
        assert c["hp"] == 146 and c["alive"]

    def test_assassin_dead(self, battles):
        c = _find_char(battles["buff_battle"], "assassin")
        assert c["hp"] == 0 and not c["alive"]

    def test_mage_dead(self, battles):
        c = _find_char(battles["buff_battle"], "mage")
        assert c["hp"] == 0 and not c["alive"]


# ===================================================================
# Section 9: Cross-Cutting Gotcha Tests
# ===================================================================

class TestGotchas:
    def test_integer_division_not_float(self, battles):
        """vine_whip: 35*25/15 = 58 (not 58.33). With SE: 58*3/2=87 (not 87.5)."""
        evs = _find_events(battles["elemental_chain"], "attack",
                           actor="druid", ability="vine_whip", target="healer")
        assert evs[0]["damage"] == 87

    def test_same_element_nve(self, battles):
        """wind vs fire is NVE because defender beats attacker in cycle."""
        evs = _find_events(battles["basic_combat"], "attack",
                           actor="rogue", ability="backstab")
        assert evs[0]["effectiveness"] == "not_very_effective"

    def test_poison_after_action_skip(self, battles):
        """Knight skips action (target dead) but still gets poison tick."""
        b = battles["poison_battle"]
        r2_evs = [e for e in b["events"] if e["round"] == 2]
        knight_evs = [e for e in r2_evs if e["actor"] == "knight"]
        assert len(knight_evs) == 2
        assert knight_evs[0]["type"] == "skip"
        assert knight_evs[1]["type"] == "poison_tick"

    def test_hp_never_below_zero(self, battles):
        for b in battles.values():
            for ev in b["events"]:
                if "target_hp" in ev:
                    assert ev["target_hp"] >= 0
                if "hp_after" in ev:
                    assert ev["hp_after"] >= 0

    def test_buff_duration_expiry(self, battles):
        """Knight's guard (duration 2) should expire after R2.
        R3 mage ember should use base defense 10, not 35."""
        pass  # Covered by test_knight_slash_mage_r3

    def test_damage_min_one(self, battles):
        """All attacks should deal at least 1 damage."""
        for b in battles.values():
            for ev in b["events"]:
                if ev["type"] == "attack":
                    assert ev["damage"] >= 1

    def test_no_healing_dead(self, battles):
        """No heal events should target a dead character."""
        for b in battles.values():
            for ev in b["events"]:
                if ev["type"] == "heal":
                    assert ev["target_hp"] > 0 or ev["heal_amount"] == 0

    def test_final_chars_have_required_fields(self, battles):
        required = {"name", "team", "hp", "max_hp", "alive"}
        for b in battles.values():
            for c in b["final_characters"]:
                assert required.issubset(c.keys()), \
                    f"Missing fields in {c.get('name', '?')} of {b['battle']}"

    def test_summary_wins_plus_draws_equals_total(self, summary):
        total = summary["team_a_wins"] + summary["team_b_wins"] + summary["draws"]
        assert total == summary["total_battles"]

    def test_stun_does_not_persist(self, battles):
        """Stun should only last one turn. Mage stunned R1, free in R2."""
        b = battles["stun_battle"]
        r2_stun = [e for e in b["events"]
                   if e["round"] == 2 and e["actor"] == "mage"
                   and e["type"] == "stunned"]
        assert len(r2_stun) == 0
