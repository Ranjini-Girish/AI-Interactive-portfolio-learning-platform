const axios = require('axios');
const ora = require('ora');
exports.run = () => axios.get('/api').then(r => console.log(r.data));
