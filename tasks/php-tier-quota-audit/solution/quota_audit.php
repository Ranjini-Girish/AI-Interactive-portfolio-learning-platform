<?php
declare(strict_types=1);

function tierKey(string $tier, array $order): array {
    $idx = array_search($tier, $order, true);
    return $idx === false ? [count($order), $tier] : [$idx, $tier];
}

function writeJson(string $path, array $obj): void {
    file_put_contents($path, json_encode($obj, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) . "\n");
}

$data = getenv('QUOTA_DATA_DIR') ?: '/app/quota_lab';
$audit = getenv('QUOTA_AUDIT_DIR') ?: '/app/audit';
if (!is_dir($audit)) {
    mkdir($audit, 0755, true);
}

$policy = json_decode(file_get_contents("$data/policy.json"), true, 512, JSON_THROW_ON_ERROR);
$events = json_decode(file_get_contents("$data/events.json"), true, 512, JSON_THROW_ON_ERROR);
$day = (int)$policy['audit_day'];
$order = $policy['tier_order'];
$caps = array_map('intval', $policy['tier_caps']);

foreach ($events['tier_derates'] ?? [] as $d) {
    if ($d['start_day'] <= $day && $day <= $d['end_day']) {
        $t = $d['tier'];
        if (isset($caps[$t])) {
            $caps[$t] = intdiv($caps[$t] * (int)$d['factor_bp'], 10000);
        }
    }
}

$frozen = [];
foreach ($events['item_freezes'] ?? [] as $f) {
    if ($f['start_day'] <= $day && $day <= $f['end_day']) {
        $frozen[$f['item_id']] = true;
    }
}

$items = [];
foreach (glob("$data/items/*.json") as $path) {
    $items[] = json_decode(file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
}
usort($items, function ($a, $b) use ($order) {
    [$ra, $ta] = tierKey($a['tier'], $order);
    [$rb, $tb] = tierKey($b['tier'], $order);
    return $ra <=> $rb ?: $ta <=> $tb ?: $a['item_id'] <=> $b['item_id'];
});

$tierRem = $caps;
$rows = [];
$sc = ['frozen' => 0, 'ok' => 0, 'shortfall' => 0];

foreach ($items as $it) {
    $iid = $it['item_id'];
    $tier = $it['tier'];
    $demand = (int)$it['demand'];
    if (isset($frozen[$iid])) {
        $rows[] = ['item_id' => $iid, 'tier' => $tier, 'status' => 'frozen', 'demand' => $demand, 'allocated' => 0];
        $sc['frozen']++;
        continue;
    }
    $left = $tierRem[$tier] ?? 0;
    $alloc = min($demand, $left);
    $tierRem[$tier] = $left - $alloc;
    $st = $alloc === $demand ? 'ok' : 'shortfall';
    $sc[$st]++;
    $rows[] = ['item_id' => $iid, 'tier' => $tier, 'status' => $st, 'demand' => $demand, 'allocated' => $alloc];
}

$touched = [];
foreach ($rows as $r) {
    if ($r['allocated'] > 0) {
        $touched[$r['tier']] = true;
    }
}
$touched = array_keys($touched);
sort($touched);

$summary = [
    'audit_day' => $day,
    'items_processed' => count($items),
    'frozen_items' => $sc['frozen'],
    'status_counts' => $sc,
    'tiers_touched' => $touched,
];

writeJson("$audit/allocations.json", ['items' => $rows]);
writeJson("$audit/summary.json", $summary);
