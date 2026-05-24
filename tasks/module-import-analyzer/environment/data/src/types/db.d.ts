export interface QueryResult { rows: any[]; count: number; }
export interface Transaction { commit(): void; rollback(): void; }
