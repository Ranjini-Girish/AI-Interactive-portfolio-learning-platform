const { z } = require('zod');
exports.validate = (s) => z.string().parse(s);
