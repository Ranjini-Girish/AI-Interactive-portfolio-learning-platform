# Import/Export Parsing Specification

## Comment Stripping

Before parsing imports and exports, strip all comments from the source:
- Single-line comments: `// ...` through end of line
- Block comments: `/* ... */` including multiline

Do NOT strip string literals that look like comments.

## Import Patterns

### Static Named Import
```
import { name1, name2 } from './module.js';
import { name1 as alias1 } from './module.js';
```
Record each imported name (use the original name, not the alias).

### Default Import
```
import defaultExport from './module.js';
```
Record as specifier type "default" with name "default".

### Namespace Import
```
import * as namespace from './module.js';
```
Record as specifier type "namespace" with name "*".

### Side-Effect Import
```
import './module.js';
```
Record with an empty specifiers array. This creates a dependency edge but imports no names.

### Combined Import
```
import defaultExport, { named1 } from './module.js';
```
Record both the default specifier and the named specifiers.

### Multi-line Imports
Imports may span multiple lines:
```
import {
  name1,
  name2,
  name3,
} from './module.js';
```

## Dynamic Imports

```
import('./module.js')
```
Record as a dynamic import. The module path is the string literal argument. Only simple string literal arguments are supported (not template literals or variables).

## Export Patterns

### Named Export Declaration
```
export const x = 1;
export let y = 2;
export var z = 3;
export function foo() {}
export class Bar {}
```
Record each exported name.

### Default Export
```
export default expression;
export default function name() {}
export default class Name {}
```
Record as having a default export. The name "default" is used.

### Re-Export (Named)
```
export { name1, name2 } from './module.js';
export { name1 as alias1 } from './module.js';
```
Record as a re-export with source module and re-exported names. Use the ORIGINAL name from the source, not the alias.

### Re-Export All
```
export * from './module.js';
```
Record as a re-export-all. This re-exports ALL named exports from the source module, but NOT the default export.

### Re-Export Default as Named
```
export { default as name } from './module.js';
```
Record as a re-export with the original name "default" and the alias "name".

## Module Path Resolution

All import/export source paths are relative (starting with `./` or `../`). Resolve them relative to the importing file's directory. The `.js` extension is always explicit in the source files; do not add it automatically.
