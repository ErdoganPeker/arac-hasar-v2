/**
 * services/storage.ts — Lightweight async key/value store wrapping AsyncStorage.
 * Used for non-sensitive cached data (history snapshots, last-seen ids, etc.).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

export async function readJSON<T>(key: string): Promise<T | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export async function writeJSON<T>(key: string, value: T): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

export async function remove(key: string): Promise<void> {
  try {
    await AsyncStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export const storage = { readJSON, writeJSON, remove };
export default storage;
