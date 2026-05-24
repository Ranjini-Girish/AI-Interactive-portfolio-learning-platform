const jwt = require('jsonwebtoken');
const bcrypt = require('bcrypt');
exports.sign = jwt.sign;
exports.hash = bcrypt.hash;
