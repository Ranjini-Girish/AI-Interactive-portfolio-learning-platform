import { VERSION } from './constants.js';

export class AppError extends Error {
  constructor(message, code = 500) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.version = VERSION;
  }
}

export class ValidationError extends AppError {
  constructor(message) {
    super(message, 400);
    this.name = 'ValidationError';
  }
}

export class AuthError extends AppError {
  constructor(message) {
    super(message, 401);
    this.name = 'AuthError';
  }
}

export class NotFoundError extends AppError {
  constructor(resource) {
    super(`${resource} not found`, 404);
    this.name = 'NotFoundError';
    this.resource = resource;
  }
}
