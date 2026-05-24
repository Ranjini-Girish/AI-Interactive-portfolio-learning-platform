const fs = require('fs');
const path = require('path');

function loadJSON(filePath) {
  const raw = fs.readFileSync(filePath, 'utf-8');
  return JSON.parse(raw);
}

function loadAllData(dataDir) {
  return {
    products:     loadJSON(path.join(dataDir, 'products.json')),
    inventory:    loadJSON(path.join(dataDir, 'inventory.json')),
    transactions: loadJSON(path.join(dataDir, 'transactions.json')),
    suppliers:    loadJSON(path.join(dataDir, 'suppliers.json')),
    categories:   loadJSON(path.join(dataDir, 'categories.json')),
    warehouses:   loadJSON(path.join(dataDir, 'warehouses.json')),
  };
}

module.exports = { loadJSON, loadAllData };
