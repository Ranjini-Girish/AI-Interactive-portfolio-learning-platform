import { authenticate } from './auth.js';
import { validateRequest } from './validators.js';
import { UserModel, OrderModel } from './models.js';

const lazyAdmin = () => import('./admin.js');

export function defineRoutes(app) {
  app.routes.push({ path: '/users', handler: listUsers });
  app.routes.push({ path: '/orders', handler: listOrders });
  app.routes.push({ path: '/admin', handler: adminPanel });
}

export function handleRequest(req) {
  authenticate(req);
  validateRequest(req.schema, req.body);
  return { status: 200 };
}

export default class Router {
  constructor() {
    this.routes = [];
  }
  add(path, handler) {
    this.routes.push({ path, handler });
  }
}

function listUsers() {
  return UserModel.findAll();
}

function listOrders() {
  return OrderModel.findAll();
}

async function adminPanel() {
  const admin = await lazyAdmin();
  return admin.listUsers();
}
