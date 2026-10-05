import { File, Paths } from 'expo-file-system';
import * as MediaLibrary from 'expo-media-library/legacy';
import * as Sharing from 'expo-sharing';

export type SaveOutcome = 'saved' | 'shared' | 'cancelled';

async function download(url: string, name: string): Promise<File> {
  const target = new File(Paths.cache, name);
  if (target.exists) target.delete(); // a re-save fetches the current image, not a stale copy
  return File.downloadFileAsync(url, target);
}

/**
 * Keep a try-on: straight into the phone's gallery when allowed (add-only access, nothing is
 * read), otherwise the system share sheet so the person can still save or send it.
 * Results on our side are deleted within 24 h, so the saved copy is theirs to keep.
 */
export async function saveImage(url: string, name: string): Promise<SaveOutcome> {
  const file = await download(url, name);
  try {
    const permission = await MediaLibrary.requestPermissionsAsync(true);
    if (permission.granted) {
      await MediaLibrary.saveToLibraryAsync(file.uri);
      return 'saved';
    }
  } catch {
    // Some environments (e.g. Expo Go on newer Android) can't write to the gallery: share instead.
  }
  return (await shareImage(file.uri)) ? 'shared' : 'cancelled';
}

export async function shareFromUrl(url: string, name: string): Promise<boolean> {
  return shareImage((await download(url, name)).uri);
}

async function shareImage(uri: string): Promise<boolean> {
  if (!(await Sharing.isAvailableAsync())) return false;
  await Sharing.shareAsync(uri, { mimeType: 'image/jpeg', dialogTitle: 'Save or share your look' });
  return true;
}
