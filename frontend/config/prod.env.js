'use strict'
module.exports = {
  NODE_ENV: '"production"',
  API_BASE: JSON.stringify(process.env.API_BASE || 'http://127.0.0.1:8080')
}
