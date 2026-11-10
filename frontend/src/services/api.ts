export let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Service is unreachable." }));
    throw new Error(error.detail || "Request failed.");
  }
  return response.json();
}
export async function synthesize(
  body: object,
): Promise<{ url: string; ms: number }> {
  const response = await fetch("/api/speech/synthesize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
  return {
    url: URL.createObjectURL(await response.blob()),
    ms: Number(response.headers.get("X-Synthesis-Ms")),
  };
}
