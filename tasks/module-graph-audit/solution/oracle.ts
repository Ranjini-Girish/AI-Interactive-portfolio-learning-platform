import { readFileSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, basename } from 'node:path';

const DATA = '/app/data';
const MODULES_DIR = join(DATA, 'modules');
const CONFIG_PATH = join(DATA, 'project_config.json');
const OUT_DIR = '/app/output';
try { mkdirSync(OUT_DIR, { recursive: true }); } catch {}

const PREC = 6;
function round6(x) {
  if (x === null || x === undefined) return null;
  if (Number.isInteger(x)) return x;
  return parseFloat(x.toFixed(PREC));
}

function stripComments(src) {
  let result = [];
  let i = 0;
  let inSingleQ = false, inDoubleQ = false, inTemplate = false;
  while (i < src.length) {
    const c = src[i];
    if (inSingleQ) {
      result.push(c);
      if (c === '\\' && i + 1 < src.length) { i++; result.push(src[i]); }
      else if (c === "'") inSingleQ = false;
      i++; continue;
    }
    if (inDoubleQ) {
      result.push(c);
      if (c === '\\' && i + 1 < src.length) { i++; result.push(src[i]); }
      else if (c === '"') inDoubleQ = false;
      i++; continue;
    }
    if (inTemplate) {
      result.push(c);
      if (c === '\\' && i + 1 < src.length) { i++; result.push(src[i]); }
      else if (c === '`') inTemplate = false;
      i++; continue;
    }
    if (c === "'") { inSingleQ = true; result.push(c); i++; continue; }
    if (c === '"') { inDoubleQ = true; result.push(c); i++; continue; }
    if (c === '`') { inTemplate = true; result.push(c); i++; continue; }
    if (c === '/' && i + 1 < src.length) {
      if (src[i+1] === '/') {
        const j = src.indexOf('\n', i);
        if (j === -1) break;
        i = j; continue;
      }
      if (src[i+1] === '*') {
        const j = src.indexOf('*/', i + 2);
        if (j === -1) break;
        i = j + 2; continue;
      }
    }
    result.push(c);
    i++;
  }
  return result.join('');
}

function resolveModulePath(relPath) {
  const parts = relPath.split('/');
  return parts[parts.length - 1];
}

function parseModule(moduleId, src) {
  const cleaned = stripComments(src);
  const info = {
    module_id: moduleId,
    source_size: Buffer.byteLength(src, 'utf8'),
    named_exports: [],
    has_default_export: false,
    re_exports: [],
    static_imports: [],
    dynamic_imports: [],
  };

  const importPat = /import\s+(?:(['"])([^'"]+)\1|(.+?)\s+from\s+(['"])([^'"]+)\4)/gs;
  let m;
  while ((m = importPat.exec(cleaned)) !== null) {
    if (m[2] !== undefined) {
      info.static_imports.push({ source: resolveModulePath(m[2]), specifiers: [] });
    } else {
      const rest = m[3].trim();
      const target = resolveModulePath(m[5]);
      const specifiers = [];
      if (rest.startsWith('* as ')) {
        specifiers.push({ type: 'namespace', name: '*' });
      } else {
        const combined = rest.match(/^(\w+)\s*,\s*\{([^}]*)\}/);
        if (combined) {
          specifiers.push({ type: 'default', name: 'default' });
          for (const n of combined[2].split(',')) {
            const t = n.trim();
            if (!t) continue;
            specifiers.push({ type: 'named', name: t.split(/\s+as\s+/)[0].trim() });
          }
        } else if (rest.startsWith('{')) {
          const brace = rest.match(/\{([^}]*)\}/);
          if (brace) {
            for (const n of brace[1].split(',')) {
              const t = n.trim();
              if (!t) continue;
              specifiers.push({ type: 'named', name: t.split(/\s+as\s+/)[0].trim() });
            }
          }
        } else if (rest && !rest.startsWith('{')) {
          specifiers.push({ type: 'default', name: 'default' });
        }
      }
      info.static_imports.push({ source: target, specifiers });
    }
  }

  const dynPat = /import\(\s*['"]([^'"]+)['"]\s*\)/g;
  while ((m = dynPat.exec(cleaned)) !== null) {
    const target = resolveModulePath(m[1]);
    if (!info.dynamic_imports.includes(target)) info.dynamic_imports.push(target);
  }

  const namedDecl = /export\s+(?:const|let|var|function\*?|class)\s+(\w+)/g;
  while ((m = namedDecl.exec(cleaned)) !== null) info.named_exports.push(m[1]);

  if (/export\s+default\s+/.test(cleaned)) info.has_default_export = true;

  const reAll = /export\s+\*\s+from\s+['"]([^'"]+)['"]/g;
  while ((m = reAll.exec(cleaned)) !== null) {
    info.re_exports.push({ source: resolveModulePath(m[1]), names: [], is_all: true });
  }

  const reNamed = /export\s+\{([^}]*)\}\s+from\s+['"]([^'"]+)['"]/g;
  while ((m = reNamed.exec(cleaned)) !== null) {
    const names = [];
    for (const n of m[1].split(',')) {
      const t = n.trim();
      if (!t) continue;
      names.push(t.split(/\s+as\s+/)[0].trim());
    }
    names.sort();
    info.re_exports.push({ source: resolveModulePath(m[2]), names, is_all: false });
  }

  info.named_exports = [...new Set(info.named_exports)].sort();
  info.dynamic_imports = [...new Set(info.dynamic_imports)].sort();
  info.static_imports.sort((a, b) => a.source.localeCompare(b.source));
  info.re_exports.sort((a, b) => a.source.localeCompare(b.source) || (a.is_all === b.is_all ? 0 : a.is_all ? 1 : -1));
  return info;
}

function buildEdges(modulesInfo) {
  const edgeSet = new Set();
  const edges = [];
  for (const mod of modulesInfo) {
    for (const imp of mod.static_imports) {
      const key = `${mod.module_id}|${imp.source}|static`;
      if (!edgeSet.has(key)) { edgeSet.add(key); edges.push({ source: mod.module_id, target: imp.source, type: 'static' }); }
    }
    for (const re of mod.re_exports) {
      const key = `${mod.module_id}|${re.source}|static`;
      if (!edgeSet.has(key)) { edgeSet.add(key); edges.push({ source: mod.module_id, target: re.source, type: 'static' }); }
    }
    for (const dyn of mod.dynamic_imports) {
      const key = `${mod.module_id}|${dyn}|dynamic`;
      if (!edgeSet.has(key)) { edgeSet.add(key); edges.push({ source: mod.module_id, target: dyn, type: 'dynamic' }); }
    }
  }
  edges.sort((a, b) => a.source.localeCompare(b.source) || a.target.localeCompare(b.target) || a.type.localeCompare(b.type));
  return edges;
}

function computeCoupling(modulesInfo, edges) {
  const ca = {}, ce = {};
  for (const e of edges) {
    if (e.type !== 'static') continue;
    ce[e.source] = (ce[e.source] || 0) + 1;
    ca[e.target] = (ca[e.target] || 0) + 1;
  }
  for (const mod of modulesInfo) {
    mod.afferent_coupling = ca[mod.module_id] || 0;
    mod.efferent_coupling = ce[mod.module_id] || 0;
    const total = mod.afferent_coupling + mod.efferent_coupling;
    mod.instability = total === 0 ? null : round6(mod.efferent_coupling / total);
  }
}

function tarjanSCC(nodes, adj) {
  let idx = 0;
  const stack = [], onStack = new Set();
  const indexMap = {}, lowlink = {};
  const sccs = [];
  function sc(v) {
    indexMap[v] = lowlink[v] = idx++;
    stack.push(v); onStack.add(v);
    for (const w of (adj[v] || [])) {
      if (indexMap[w] === undefined) { sc(w); lowlink[v] = Math.min(lowlink[v], lowlink[w]); }
      else if (onStack.has(w)) { lowlink[v] = Math.min(lowlink[v], indexMap[w]); }
    }
    if (lowlink[v] === indexMap[v]) {
      const scc = [];
      while (true) { const w = stack.pop(); onStack.delete(w); scc.push(w); if (w === v) break; }
      sccs.push(scc.sort());
    }
  }
  for (const n of [...nodes].sort()) { if (indexMap[n] === undefined) sc(n); }
  return sccs;
}

function findCircularDeps(modulesInfo, edges) {
  const nodes = new Set(modulesInfo.map(m => m.module_id));
  const adj = {};
  for (const e of edges) { if (e.type === 'static') { (adj[e.source] = adj[e.source] || []).push(e.target); } }
  const sccs = tarjanSCC(nodes, adj);
  const multi = sccs.filter(s => s.length >= 2).sort((a, b) => a[0].localeCompare(b[0]));
  return multi.map((scc, i) => ({ cycle_id: i + 1, modules: scc, representative: scc[0] }));
}

function computeLayers(modulesInfo, edges, circDeps) {
  const sccMap = {};
  for (const cd of circDeps) { for (const m of cd.modules) sccMap[m] = cd.representative; }
  for (const mod of modulesInfo) { if (!sccMap[mod.module_id]) sccMap[mod.module_id] = mod.module_id; }
  const condensedAdj = {};
  for (const e of edges) {
    if (e.type !== 'static') continue;
    const s = sccMap[e.source], t = sccMap[e.target];
    if (s !== t) { (condensedAdj[s] = condensedAdj[s] || new Set()).add(t); }
  }
  const cache = {};
  function getLayer(node) {
    if (cache[node] !== undefined) return cache[node];
    cache[node] = -1;
    const deps = condensedAdj[node];
    if (!deps || deps.size === 0) { cache[node] = 0; }
    else { let mx = 0; for (const d of deps) mx = Math.max(mx, getLayer(d)); cache[node] = 1 + mx; }
    return cache[node];
  }
  const allNodes = new Set(Object.values(sccMap));
  for (const n of allNodes) getLayer(n);
  for (const mod of modulesInfo) mod.layer = cache[sccMap[mod.module_id]];
}

function getEffectiveNamedExports(moduleId, dict, visited = new Set()) {
  if (visited.has(moduleId)) return new Set();
  visited.add(moduleId);
  const mod = dict[moduleId];
  if (!mod) return new Set();
  const result = new Set(mod.named_exports);
  for (const re of mod.re_exports) {
    if (re.is_all) {
      for (const n of getEffectiveNamedExports(re.source, dict, new Set(visited))) result.add(n);
    }
  }
  return result;
}

function treeShaking(config, modulesInfo, edges) {
  const dict = {};
  for (const m of modulesInfo) dict[m.module_id] = m;
  const reachable = new Set();
  const usedExports = {};
  const addUsed = (mid, name) => { (usedExports[mid] = usedExports[mid] || new Set()).add(name); };
  const toProcess = [...config.entry_points];
  while (toProcess.length > 0) {
    const mid = toProcess.pop();
    if (reachable.has(mid)) continue;
    reachable.add(mid);
    const mod = dict[mid];
    if (!mod) continue;
    for (const imp of mod.static_imports) {
      if (!reachable.has(imp.source)) toProcess.push(imp.source);
      for (const spec of imp.specifiers) {
        if (spec.type === 'named') addUsed(imp.source, spec.name);
        else if (spec.type === 'default') addUsed(imp.source, 'default');
        else if (spec.type === 'namespace') {
          for (const n of getEffectiveNamedExports(imp.source, dict)) addUsed(imp.source, n);
        }
      }
    }
    for (const re of mod.re_exports) { if (!reachable.has(re.source)) toProcess.push(re.source); }
    for (const dyn of mod.dynamic_imports) {
      if (!reachable.has(dyn)) toProcess.push(dyn);
      const dm = dict[dyn];
      if (dm) {
        for (const n of dm.named_exports) addUsed(dyn, n);
        if (dm.has_default_export) addUsed(dyn, 'default');
        for (const n of getEffectiveNamedExports(dyn, dict)) addUsed(dyn, n);
      }
    }
  }

  // Propagate used exports through re-export chains
  let changed = true;
  const modulesSrc = {};
  for (const f of readdirSync(MODULES_DIR)) {
    if (f.endsWith('.js')) modulesSrc[f] = readFileSync(join(MODULES_DIR, f), 'utf8');
  }
  while (changed) {
    changed = false;
    for (const mid of reachable) {
      const mod = dict[mid];
      if (!mod) continue;
      for (const re of mod.re_exports) {
        if (re.is_all) {
          const childEff = getEffectiveNamedExports(re.source, dict);
          const used = usedExports[mid] || new Set();
          for (const name of used) {
            if (name !== 'default' && childEff.has(name)) {
              if (!usedExports[re.source] || !usedExports[re.source].has(name)) {
                addUsed(re.source, name); changed = true;
              }
            }
          }
        } else {
          for (const origName of re.names) {
            let alias = null;
            const srcText = modulesSrc[mid];
            if (srcText) {
              const cl = stripComments(srcText);
              const pat = new RegExp(`export\\s+\\{([^}]*)\\}\\s+from\\s+['\"]\\.\\/` + re.source.replace('.', '\\.') + `['\"]`);
              const em = cl.match(pat);
              if (em) {
                for (const item of em[1].split(',')) {
                  const parts = item.trim().split(/\s+as\s+/);
                  if (parts.length === 2 && parts[0].trim() === origName) alias = parts[1].trim();
                }
              }
            }
            const checkName = alias || origName;
            if (usedExports[mid] && usedExports[mid].has(checkName)) {
              if (!usedExports[re.source] || !usedExports[re.source].has(origName)) {
                addUsed(re.source, origName); changed = true;
              }
            }
          }
        }
      }
    }
  }

  const allMods = new Set(modulesInfo.map(m => m.module_id));
  const unreachable = [...allMods].filter(m => !reachable.has(m)).sort();
  const usedOut = {}, unusedOut = {};
  for (const mid of [...allMods].sort()) {
    if (!reachable.has(mid)) continue;
    const mod = dict[mid];
    const allExports = new Set(mod.named_exports);
    if (mod.has_default_export) allExports.add('default');
    const used = new Set([...(usedExports[mid] || [])].filter(n => allExports.has(n)));
    const unused = new Set([...allExports].filter(n => !used.has(n)));
    if (used.size > 0) usedOut[mid] = [...used].sort();
    if (unused.size > 0) unusedOut[mid] = [...unused].sort();
  }

  const origSize = modulesInfo.reduce((s, m) => s + m.source_size, 0);
  const tsSize = modulesInfo.filter(m => reachable.has(m.module_id)).reduce((s, m) => s + m.source_size, 0);
  const savings = origSize > 0 ? round6((origSize - tsSize) / origSize) : 0.0;

  return {
    entry_points: [...config.entry_points].sort(),
    reachable_modules: [...reachable].sort(),
    unreachable_modules: unreachable,
    used_exports: usedOut,
    unused_exports: unusedOut,
    original_size: origSize,
    tree_shaken_size: tsSize,
    savings_ratio: savings,
  };
}

// --- Main ---
const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
const files = readdirSync(MODULES_DIR).filter(f => f.endsWith('.js')).sort();
const modulesInfo = files.map(f => parseModule(f, readFileSync(join(MODULES_DIR, f), 'utf8')));
const edges = buildEdges(modulesInfo);
computeCoupling(modulesInfo, edges);
const circDeps = findCircularDeps(modulesInfo, edges);
computeLayers(modulesInfo, edges, circDeps);
const ts = treeShaking(config, modulesInfo, edges);

const n = modulesInfo.length;
const summary = {
  total_modules: n,
  total_static_edges: edges.filter(e => e.type === 'static').length,
  total_dynamic_edges: edges.filter(e => e.type === 'dynamic').length,
  circular_dependency_count: circDeps.length,
  total_named_exports: modulesInfo.reduce((s, m) => s + m.named_exports.length, 0),
  total_re_exports: modulesInfo.reduce((s, m) => s + m.re_exports.length, 0),
  modules_with_default_export: modulesInfo.filter(m => m.has_default_export).length,
  side_effect_only_imports: modulesInfo.reduce((s, m) => s + m.static_imports.filter(i => i.specifiers.length === 0).length, 0),
  avg_afferent_coupling: round6(modulesInfo.reduce((s, m) => s + m.afferent_coupling, 0) / n),
  avg_efferent_coupling: round6(modulesInfo.reduce((s, m) => s + m.efferent_coupling, 0) / n),
};

const report = {
  config,
  modules: modulesInfo.sort((a, b) => a.module_id.localeCompare(b.module_id)),
  dependency_edges: edges,
  circular_dependencies: circDeps,
  tree_shaking: ts,
  summary,
};

writeFileSync(join(OUT_DIR, 'module_report.json'), JSON.stringify(report, null, 2) + '\n', 'utf8');
