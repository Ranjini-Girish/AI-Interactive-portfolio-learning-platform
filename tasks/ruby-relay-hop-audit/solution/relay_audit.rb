#!/usr/bin/env ruby
# frozen_string_literal: true

require 'json'

def env_or(key, default)
  v = ENV[key]
  v.nil? || v.empty? ? default : v
end

def read_json(path)
  JSON.parse(File.read(path))
end

def write_json(path, obj)
  File.write(path, JSON.pretty_generate(obj) + "\n")
end

def sorted_glob(dir, suffix)
  Dir.glob(File.join(dir, "*#{suffix}")).sort
end

def cap_core(h, base, delta, halted)
  return 0 if halted[h]
  v = base[h] + delta[h]
  v < 1 ? 1 : v
end

data_dir = env_or('RBH_DATA_DIR', '/app/relayhop')
audit_dir = env_or('RBH_AUDIT_DIR', '/app/audit')
Dir.mkdir(audit_dir) unless Dir.exist?(audit_dir)

pol = read_json(File.join(data_dir, 'policy.json'))
inc_file = read_json(File.join(data_dir, 'incidents.json'))
carry_max = pol['carry_max']
epochs = pol['epochs']
hops_order = pol['hops_order']

base = {}
sorted_glob(File.join(data_dir, 'hops'), '.json').each do |p|
  hf = read_json(p)
  base[hf['hop_id']] = hf['base_cap']
end

flows = []
sorted_glob(File.join(data_dir, 'flows'), '.json').each do |p|
  ff = read_json(p)
  flows << {
    flow_id: ff['flow_id'],
    epoch: ff['epoch'],
    hop_id: ff['hop_id'],
    bytes: ff['bytes']
  }
end

epoch_set = epochs.to_h { |e| [e, true] }
flows.each do |f|
  raise 'bad fixture' unless epoch_set[f[:epoch]] && base[f[:hop_id]]
end
raise 'hops_order mismatch' unless hops_order.uniq.length == hops_order.length &&
                                   hops_order.length == base.length &&
                                   base.keys.all? { |h| hops_order.include?(h) }

delta = hops_order.to_h { |h| [h, 0] }
carry = hops_order.to_h { |h| [h, 0] }
halted = hops_order.to_h { |h| [h, false] }

admissions = []
denials = []
ledgers = []

epochs.each do |e|
  inc_file['incidents'].each do |inc|
    next unless inc['epoch'] == e
    kind = inc['kind']
    next if kind == 'noop'
    h = inc['hop_id']
    case kind
    when 'cap_add' then delta[h] += inc['delta']
    when 'halt_hop' then halted[h] = true; carry[h] = 0
    when 'resume_hop' then halted[h] = false; carry[h] = 0
    else raise 'unknown kind'
    end
  end

  cin = hops_order.to_h { |h| [h, carry[h]] }
  used = hops_order.to_h { |h| [h, 0] }

  epoch_flows = flows.select { |f| f[:epoch] == e }
  epoch_flows.sort_by! { |f| [f[:hop_id], f[:flow_id]] }

  epoch_flows.each do |f|
    h = f[:hop_id]
    b = f[:bytes]
    avail = cap_core(h, base, delta, halted) + cin[h] - used[h]
    avail = 0 if avail.negative?
    if b <= avail
      used[h] += b
      admissions << { bytes: b, epoch: e, flow_id: f[:flow_id], hop_id: h }
    else
      denials << { available: avail, epoch: e, flow_id: f[:flow_id], hop_id: h, requested: b }
    end
  end

  hops_order.each do |h|
    cc = cap_core(h, base, delta, halted)
    rem = cc + cin[h] - used[h]
    cout = [carry_max, [0, rem].max].min
    cout = 0 if halted[h]
    ledgers << { cap_core: cc, carry_in: cin[h], carry_out: cout, epoch: e, hop_id: h, used: used[h] }
    carry[h] = cout
  end
end

admissions.sort_by! { |r| [r[:epoch], r[:hop_id], r[:flow_id]] }
denials.sort_by! { |r| [r[:epoch], r[:hop_id], r[:flow_id]] }
ledgers.sort_by! { |r| [r[:epoch], r[:hop_id]] }

applied = inc_file['incidents'].map { |inc| inc['kind'] }
max_ep = 0
inc_file['incidents'].each { |inc| max_ep = [max_ep, inc['epoch']].max }
admissions.each { |a| max_ep = [max_ep, a[:epoch]].max }
denials.each { |d| max_ep = [max_ep, d[:epoch]].max }

write_json(File.join(audit_dir, 'admissions.json'), 'admissions' => admissions)
write_json(File.join(audit_dir, 'denials.json'), 'denials' => denials)
write_json(File.join(audit_dir, 'carry_ledgers.json'), 'rows' => ledgers)
write_json(File.join(audit_dir, 'summary.json'),
           'incidents_applied' => applied,
           'max_epoch' => max_ep,
           'total_admissions' => admissions.length,
           'total_admitted_bytes' => admissions.sum { |a| a[:bytes] },
           'total_denials' => denials.length,
           'total_denied_bytes' => denials.sum { |d| d[:requested] })
