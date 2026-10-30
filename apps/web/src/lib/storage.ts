/** Small per-browser conveniences; storage can be unavailable, so every access is guarded. */
export const LAST_PROJECT_KEY = "ragkit-last-project";
export const PLAYGROUND_KEY = "ragkit-playground";

export function readLocal(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeLocal(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage blocked (private mode, policy): the preference just is not remembered.
  }
}
