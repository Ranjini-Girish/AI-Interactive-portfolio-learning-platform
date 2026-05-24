'use strict';

const fs = require('fs');

function load(configPath) {
    const raw = fs.readFileSync(configPath, 'utf-8');
    return JSON.parse(raw);
}

module.exports = { load };
