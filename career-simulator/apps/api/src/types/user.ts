export type DbUser = {
  id: string;
  email: string;
  password_hash: string | null;
  full_name: string;
  clerk_id: string | null;
  created_at: Date;
  updated_at: Date;
};

export type UserRow = {
  id: string;
  email: string;
  full_name: string;
  created_at: Date;
};
