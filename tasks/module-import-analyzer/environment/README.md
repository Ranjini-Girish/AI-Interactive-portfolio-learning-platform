# JavaScript Module Import/Export Analyzer

## Data Layout

```
data/
  entry-points.json    Entry point module list
  package.json         Project package configuration
  tsconfig.json        TypeScript configuration
  .eslintrc.json       ESLint configuration
  src/                 JavaScript ES module source files
    index.js
    app.js
    router.js
    middleware.js
    auth.js
    crypto-utils.js
    config.js
    defaults.js
    env-loader.js
    validators.js
    constants.js
    helpers.js
    logger.js
    formatters.js
    db.js
    polyfills.js
    unused-util.js
    event-bus.js
    handlers/
      user.js
      product.js
      order.js
docs/
  IMPORT_RULES.md      Import/export recognition patterns
  OUTPUT_FORMAT.md      Output JSON schema specification
```
