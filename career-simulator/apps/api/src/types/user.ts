export type DbUser = {
  id: string;
  email: string;
  password_hash: string;
  full_name: string;
  created_at: Date;
  updated_at: Date;
};

export type UserRow = {
  id: string;
  email: string;
  full_name: string;
  created_at: Date;
};
