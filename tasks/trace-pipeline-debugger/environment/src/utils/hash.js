'use strict';

const crypto = require('crypto');

function hashString(str) {
    return crypto.createHash('sha256').update(str, 'utf-8').digest('hex');
}

module.exports = { hashString };
