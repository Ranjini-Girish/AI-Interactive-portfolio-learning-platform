export type UserPublic = {
  id: string;
  email: string;
  fullName: string;
  createdAt: string;
};

export type RegisterRequest = {
  email: string;
  password: string;
  fullName: string;
};

export type LoginRequest = {
  email: string;
  password: string;
};

export type AuthResponse = {
  token: string;
  user: UserPublic;
};

export type MeResponse = {
  user: UserPublic;
};
