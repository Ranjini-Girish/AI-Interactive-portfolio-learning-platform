<?php
declare(strict_types=1);

function env_or(string $key, string $default): string {
    $v = getenv($key);
    return ($v !== false && $v !== '') ? $v : $default;
}

function read_json(string $path): array {
    $raw = file_get_contents($path);
    if ($raw === false) {
        throw new RuntimeException("read failed: $path");
    }
    $j = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
    if (!is_array($j)) {
        throw new RuntimeException("not object: $path");
    }
    return $j;
}

function write_json(string $path, array $obj): void {
    file_put_contents($path, json_encode($obj, JSON_PRETTY_PRINT) . "\n");
}

/** @return list<string> */
function sorted_glob(string $dir, string $suffix): array {
    $out = [];
    foreach (glob($dir . '/*' . $suffix) ?: [] as $p) {
        $out[] = $p;
    }
    sort($out, SORT_STRING);
    return $out;
}

function cap_core(string $h, array $base, array $delta, array $halted): int {
    if (!empty($halted[$h])) {
        return 0;
    }
    $v = $base[$h] + $delta[$h];
    return $v < 1 ? 1 : $v;
}

function main(): int {
    $dataDir = env_or('PRH_DATA_DIR', '/app/relayhop');
    $auditDir = env_or('PRH_AUDIT_DIR', '/app/audit');
    if (!is_dir($auditDir) && !mkdir($auditDir, 0755, true) && !is_dir($auditDir)) {
        return 1;
    }

    $pol = read_json("$dataDir/policy.json");
    $incFile = read_json("$dataDir/incidents.json");
    $carryMax = (int)$pol['carry_max'];
    $epochs = $pol['epochs'];
    $hopsOrder = $pol['hops_order'];

    $base = [];
    foreach (sorted_glob("$dataDir/hops", '.json') as $p) {
        $hf = read_json($p);
        $base[$hf['hop_id']] = (int)$hf['base_cap'];
    }

    $flows = [];
    foreach (sorted_glob("$dataDir/flows", '.json') as $p) {
        $ff = read_json($p);
        $flows[] = [
            'flow_id' => $ff['flow_id'],
            'epoch' => (int)$ff['epoch'],
            'hop_id' => $ff['hop_id'],
            'bytes' => (int)$ff['bytes'],
        ];
    }

    $epochSet = array_flip($epochs);
    foreach ($flows as $f) {
        if (!isset($epochSet[$f['epoch']]) || !isset($base[$f['hop_id']])) {
            return 1;
        }
    }
    if (count(array_unique($hopsOrder)) !== count($hopsOrder) || count($hopsOrder) !== count($base)) {
        return 1;
    }
    foreach (array_keys($base) as $h) {
        if (!in_array($h, $hopsOrder, true)) {
            return 1;
        }
    }

    $delta = $carry = $halted = [];
    foreach ($hopsOrder as $h) {
        $delta[$h] = 0;
        $carry[$h] = 0;
        $halted[$h] = false;
    }

    $admissions = [];
    $denials = [];
    $ledgers = [];

    foreach ($epochs as $e) {
        $e = (int)$e;
        foreach ($incFile['incidents'] as $inc) {
            if ((int)$inc['epoch'] !== $e) {
                continue;
            }
            $kind = $inc['kind'];
            if ($kind === 'noop') {
                continue;
            }
            $h = $inc['hop_id'];
            if ($kind === 'cap_add') {
                $delta[$h] += (int)$inc['delta'];
            } elseif ($kind === 'halt_hop') {
                $halted[$h] = true;
                $carry[$h] = 0;
            } elseif ($kind === 'resume_hop') {
                $halted[$h] = false;
                $carry[$h] = 0;
            } else {
                return 1;
            }
        }

        $cin = [];
        $used = [];
        foreach ($hopsOrder as $h) {
            $cin[$h] = $carry[$h];
            $used[$h] = 0;
        }

        $epochFlows = array_values(array_filter($flows, fn($f) => $f['epoch'] === $e));
        usort($epochFlows, function ($a, $b) {
            if ($a['hop_id'] !== $b['hop_id']) {
                return $a['hop_id'] <=> $b['hop_id'];
            }
            return $a['flow_id'] <=> $b['flow_id'];
        });

        foreach ($epochFlows as $f) {
            $h = $f['hop_id'];
            $b = $f['bytes'];
            $bud = cap_core($h, $base, $delta, $halted) + $cin[$h];
            $avail = $bud - $used[$h];
            if ($avail < 0) {
                $avail = 0;
            }
            if ($b <= $avail) {
                $used[$h] += $b;
                $admissions[] = [
                    'bytes' => $b,
                    'epoch' => $e,
                    'flow_id' => $f['flow_id'],
                    'hop_id' => $h,
                ];
            } else {
                $denials[] = [
                    'available' => $avail,
                    'epoch' => $e,
                    'flow_id' => $f['flow_id'],
                    'hop_id' => $h,
                    'requested' => $b,
                ];
            }
        }

        foreach ($hopsOrder as $h) {
            $cc = cap_core($h, $base, $delta, $halted);
            $bud = $cc + $cin[$h];
            $u = $used[$h];
            $rem = $bud - $u;
            $cout = min($carryMax, max(0, $rem));
            if ($halted[$h]) {
                $cout = 0;
            }
            $ledgers[] = [
                'cap_core' => $cc,
                'carry_in' => $cin[$h],
                'carry_out' => $cout,
                'epoch' => $e,
                'hop_id' => $h,
                'used' => $u,
            ];
            $carry[$h] = $cout;
        }
    }

    $sortRows = function (array &$rows, bool $withFlow): void {
        usort($rows, function ($a, $b) use ($withFlow) {
            if ($a['epoch'] !== $b['epoch']) {
                return $a['epoch'] <=> $b['epoch'];
            }
            if ($a['hop_id'] !== $b['hop_id']) {
                return $a['hop_id'] <=> $b['hop_id'];
            }
            if ($withFlow) {
                return $a['flow_id'] <=> $b['flow_id'];
            }
            return 0;
        });
    };
    $sortRows($admissions, true);
    $sortRows($denials, true);
    usort($ledgers, function ($a, $b) {
        if ($a['epoch'] !== $b['epoch']) {
            return $a['epoch'] <=> $b['epoch'];
        }
        return $a['hop_id'] <=> $b['hop_id'];
    });

    $applied = array_map(fn($inc) => $inc['kind'], $incFile['incidents']);
    $maxEp = 0;
    foreach ($incFile['incidents'] as $inc) {
        $maxEp = max($maxEp, (int)$inc['epoch']);
    }
    foreach ($admissions as $a) {
        $maxEp = max($maxEp, (int)$a['epoch']);
    }
    foreach ($denials as $d) {
        $maxEp = max($maxEp, (int)$d['epoch']);
    }

    $totAdm = count($admissions);
    $totAdmBytes = array_sum(array_column($admissions, 'bytes'));
    $totDen = count($denials);
    $totDenBytes = array_sum(array_column($denials, 'requested'));

    write_json("$auditDir/admissions.json", ['admissions' => $admissions]);
    write_json("$auditDir/denials.json", ['denials' => $denials]);
    write_json("$auditDir/carry_ledgers.json", ['rows' => $ledgers]);
    write_json("$auditDir/summary.json", [
        'incidents_applied' => $applied,
        'max_epoch' => $maxEp,
        'total_admissions' => $totAdm,
        'total_admitted_bytes' => $totAdmBytes,
        'total_denials' => $totDen,
        'total_denied_bytes' => $totDenBytes,
    ]);
    return 0;
}

exit(main());
