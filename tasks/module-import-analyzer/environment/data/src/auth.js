import { hashPassword, verifyToken } from './crypto-utils';
import { loadConfig } from './config';
export function authenticate() { return verifyToken(loadConfig().secret); }
export function authorize(role) { return role === 'admin'; }
export default class AuthService {
    constructor() { this.hash = hashPassword; }
}
