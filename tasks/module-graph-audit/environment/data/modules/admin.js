import { authenticate } from './auth.js';
import { UserModel } from './models.js';

export function listUsers() {
  return UserModel.findAll();
}

export function deleteUser(id) {
  const user = UserModel.findAll().rows.find(u => u.id === id);
  if (!user) throw new Error('User not found');
  return { deleted: true, id };
}

export default class AdminPanel {
  constructor(config) {
    this.config = config;
  }

  getStats() {
    return {
      users: UserModel.findAll().rows.length,
      version: this.config.version,
    };
  }
}
