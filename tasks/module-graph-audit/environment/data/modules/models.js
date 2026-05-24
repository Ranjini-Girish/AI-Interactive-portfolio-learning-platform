import { getConnection, query } from './db.js';
import { validateField } from './validators.js';

export class UserModel {
  constructor(data) {
    this.id = data.id;
    this.name = validateField('name', data.name);
    this.email = validateField('email', data.email);
  }

  static findAll() {
    return query('SELECT * FROM users');
  }

  save() {
    const conn = getConnection();
    return conn.execute('INSERT INTO users VALUES (?, ?, ?)',
      [this.id, this.name, this.email]);
  }
}

export class OrderModel {
  constructor(data) {
    this.id = data.id;
    this.userId = data.userId;
    this.total = data.total;
  }

  static findAll() {
    return query('SELECT * FROM orders');
  }
}

export class ProductModel {
  constructor(data) {
    this.id = data.id;
    this.name = validateField('name', data.name);
    this.price = data.price;
  }

  static findAll() {
    return query('SELECT * FROM products');
  }
}
