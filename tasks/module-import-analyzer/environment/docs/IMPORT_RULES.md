# Import/Export Recognition Rules

The analyzer must recognize these ES module statement forms:

## Import Forms
- Named: `import { x } from './mod'` or `import { x as y } from './mod'`
- Default: `import x from './mod'`
- Namespace: `import * as x from './mod'`
- Side-effect: `import './mod'`

## Export Forms
- Named declaration: `export function f()`, `export const x`, `export class C`
- Named list: `export { x, y }`
- Default: `export default expr`, `export default function f()`, `export default class C`
- Re-export named: `export { x } from './mod'`, `export { x as y } from './mod'`
- Re-export default-as-named: `export { default as Name } from './mod'`
- Re-export all: `export * from './mod'`

## Scope Rules
- Only internal modules (paths starting with `./` or `../`) are analyzed
- External packages (bare specifiers like `lodash`) are ignored
- `export * from './mod'` re-exports ALL named exports (NOT default)
- `import * as ns from './mod'` counts all named exports of mod as "used"
- Re-exports (`export { x } from` and `export * from`) count as uses of
  the source module's exports
