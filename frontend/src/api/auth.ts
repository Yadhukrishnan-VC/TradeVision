// Auth API module — login, refresh, /auth/me/, API-key management.
// SOURCE: 03_AUTHENTICATION.md, 04_API_CONTRACT.md.
// Per decision #2: Bearer JWT for normal frontend requests. API-key support
// is built ONLY because /auth/api-keys/ is in the contract; it remains
// isolated and not auto-applied to any specific data endpoint.

import { apiGet, apiPost, apiDelete, postLogin } from "./client";
import type {
  ApiKey,
  ApiKeyCreateRequest,
  LoginResponse,
  UserResponse,
} from "@/types/auth";

export { postLogin };

export async function getMe(): Promise<UserResponse> {
  return apiGet<UserResponse>("/auth/me/");
}

export async function listApiKeys(): Promise<ApiKey[]> {
  // ⚠ exact body NOT VERIFIED. Endpoint may return paginated or bare list.
  // Try bare first; if it looks paginated, unwrap.
  const res = await apiGet<unknown>("/auth/api-keys/");
  if (Array.isArray(res)) return res as ApiKey[];
  if (
    res &&
    typeof res === "object" &&
    "results" in res &&
    Array.isArray((res as { results: unknown }).results)
  ) {
    return (res as { results: ApiKey[] }).results;
  }
  // Unknown shape — return empty defensively.
  return [];
}

export async function createApiKey(body: ApiKeyCreateRequest): Promise<ApiKey> {
  return apiPost<ApiKey>("/auth/api-keys/", body);
}

export async function deleteApiKey(id: string): Promise<void> {
  await apiDelete<void>(`/auth/api-keys/${id}/`);
}

/** Type narrowing helper for the login response. */
export function isLoginResponse(v: unknown): v is LoginResponse {
  return (
    !!v &&
    typeof v === "object" &&
    typeof (v as LoginResponse).access === "string" &&
    typeof (v as LoginResponse).refresh === "string"
  );
}
