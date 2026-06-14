export const inferenceCorsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export function jsonWithCors<T>(data: T, init?: ResponseInit) {
  return Response.json(data, {
    ...init,
    headers: { ...inferenceCorsHeaders, ...(init?.headers ?? {}) },
  });
}
