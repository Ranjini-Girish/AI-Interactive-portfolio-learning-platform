const helmet = require('helmet');
exports.secure = (app) => app.use(helmet());
