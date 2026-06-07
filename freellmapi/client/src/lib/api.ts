const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const storedKey = localStorage.getItem('freellmapi_admin_key') || '';
  
  const headers = new Headers(options?.headers);
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  if (storedKey) {
    headers.set('Authorization', `Bearer ${storedKey}`);
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    // Clear the cached key as it is invalid/expired
    localStorage.removeItem('freellmapi_admin_key');
    // Prompt the user to input their Unified API Key
    const newKey = prompt('Please enter your Unified API Key to access the dashboard:');
    if (newKey) {
      localStorage.setItem('freellmapi_admin_key', newKey.trim());
      // Retry the request with the newly entered key
      return apiFetch<T>(path, options);
    } else {
      throw new Error('Unauthorized. Unified API Key required to access the dashboard.');
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: { message: res.statusText } }));
    throw new Error(body.error?.message ?? `HTTP ${res.status}`);
  }
  return res.json();
}
