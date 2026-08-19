// Common API contracts — error envelope, pagination envelope.
// SOURCE: 01_SYSTEM_ARCHITECTURE.md, 04_API_CONTRACT.md, 07_DATA_STATES_AND_RESEARCH.md.

/** Verified domain error envelope. */
export interface ApiErrorEnvelope {
  error: {
    code: string; // snake_case_code
    message: string;
    details?: unknown;
  };
}

/** DRF field-error shape (returned by serializer validation via raise_exception=True). */
export type DrfFieldErrors = Record<string, string[] | string> & {
  detail?: string;
};

/** Verified paginated list envelope. PAGE_SIZE=20. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Normalized error returned by the API client regardless of source shape. */
export interface NormalizedApiError {
  /** True if the body matched {error:{code,message}}; false if DRF field-errors or network. */
  isEnvelope: boolean;
  code: string | null;
  message: string;
  /** Field-level messages when DRF serializer errors were present. */
  fieldErrors?: Record<string, string[]>;
  /** Original HTTP status code if available. */
  status: number | null;
  /** True for network failures (no response). */
  isNetwork: boolean;
}

/** HTTP status codes the UI treats specially. */
export const HttpStatus = {
  Unauthorized: 401,
  Forbidden: 403,
  NotFound: 404,
  Conflict: 409,
  Unprocessable: 422,
  TooManyRequests: 429,
  ServerError: 500,
  Network: 0,
} as const;
