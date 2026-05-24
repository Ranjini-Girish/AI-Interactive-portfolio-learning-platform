import { createApp } from './app.js';
import { loadConfig } from './config.js';
import './polyfill.js';

const cfg = loadConfig();
const app = createApp(cfg);
app.listen(cfg.port);
