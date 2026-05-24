const _ = require('lodash');
const { v4 } = require('uuid');
module.exports = { validate: require('./lib').validate, id: v4 };
