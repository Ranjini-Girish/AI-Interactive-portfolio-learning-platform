const PRODUCT_ID_PATTERN = /^[A-Z]{2,4}-[A-Z]*-?\d{3}$/g;

function validateProductIds(products) {
  const results = { valid: [], invalid: [] };

  for (const product of products) {
    if (PRODUCT_ID_PATTERN.test(product.id)) {
      results.valid.push(product.id);
    } else {
      results.invalid.push(product.id);
    }
  }

  return results;
}

module.exports = { validateProductIds };
