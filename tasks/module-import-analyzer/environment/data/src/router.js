import { handleUser } from './handlers/user';
import { handleProduct } from './handlers/product';
import { handleOrder } from './handlers/order';
import { applyMiddleware } from './middleware';
export function createRouter() { applyMiddleware(); }
export function getRoutes() { return [handleUser, handleProduct, handleOrder]; }
