import { supabase } from './supabase';

/**
 * Synchronous public URL — only works if the bucket is set to public.
 */
export function photoUrl(path?: string | null): string | null {
  if (!path) return null;
  const { data } = supabase.storage.from('schaeden_fotos').getPublicUrl(path);
  return data.publicUrl;
}

/**
 * Async signed URL — works with private buckets. Preferred for fetching photos.
 */
export async function getSignedPhotoUrl(path: string): Promise<string | null> {
  const { data, error } = await supabase.storage
    .from('schaeden_fotos')
    .createSignedUrl(path, 60 * 60); // 1 hour
  if (error) {
    console.warn('[storage] signed URL error:', path, error.message);
    return null;
  }
  return data.signedUrl;
}

/**
 * Async signed URL for bridge PDF documents (bauwerksbuecher bucket).
 */
export async function getSignedPdfUrl(path: string): Promise<string | null> {
  const { data, error } = await supabase.storage
    .from('bauwerksbuecher')
    .createSignedUrl(path, 60 * 60); // 1 hour
  if (error) {
    console.warn('[storage] PDF signed URL error:', path, error.message);
    return null;
  }
  return data.signedUrl;
}
