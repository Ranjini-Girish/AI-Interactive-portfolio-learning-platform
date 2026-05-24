const fs = require('fs');
const path = require('path');

function sortByName(items) {
  return items.sort((a, b) => a.name > b.name);
}

function writeReport(report, outputDir, outputFile) {
  const outPath = path.join(outputDir, outputFile);
  fs.mkdirSync(outputDir, { recursive: true });

  if (report.product_ranking) {
    report.product_ranking = sortByName(report.product_ranking);
  }

  const json = JSON.stringify(report, null, 2) + '\n';
  fs.writeFileSync(outPath, json, 'utf-8');
  return outPath;
}

module.exports = { writeReport, sortByName };
