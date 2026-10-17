import { File } from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';

import { ApiError } from '@/api/errors';
import { api } from '@/auth/session';

export type UploadKind = 'photo_search' | 'selfie';

export interface UploadView {
  id: string;
  kind: UploadKind;
  status: 'pending' | 'ready' | 'rejected' | 'deleted';
  expires_at: string;
  url?: string | null;
  upload?: { url: string; fields: Record<string, string> } | null;
}

/** Camera or library; null when the person cancels or refuses permission. */
export async function pickPhoto(source: 'camera' | 'library', kind: UploadKind): Promise<string | null> {
  const permission =
    source === 'camera' ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!permission.granted) throw new ApiError({ status: 0, code: 'permission_denied', title: 'Permission needed' });
  const options: ImagePicker.ImagePickerOptions = {
    mediaTypes: ['images'],
    quality: 0.85,
    allowsEditing: kind === 'photo_search', // crop to the garment
    cameraType: kind === 'selfie' ? ImagePicker.CameraType.front : ImagePicker.CameraType.back,
  };
  const result = source === 'camera' ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
  return result.canceled ? null : (result.assets[0]?.uri ?? null);
}

/**
 * Signed direct upload (ADR 0016): ask our API for a slot, POST the file straight to Cloudinary,
 * then confirm so the server inspects it. The photo is deleted for good within 24 h.
 */
export async function uploadPhoto(uri: string, kind: UploadKind): Promise<UploadView> {
  const slot = await api.post<UploadView>('/v1/uploads', { kind });
  if (!slot.upload) throw new ApiError({ status: 500, code: 'upload_failed', title: 'Upload slot missing' });
  const form = new FormData();
  for (const [k, v] of Object.entries(slot.upload.fields)) form.append(k, v);
  form.append('file', new File(uri) as unknown as Blob);
  const sent = await fetch(slot.upload.url, { method: 'POST', body: form }).catch(() => null);
  if (!sent?.ok) throw new ApiError({ status: sent?.status ?? 0, code: 'upload_failed', title: "Couldn't upload that photo" });
  const view = await api.post<UploadView>(`/v1/uploads/${slot.id}/confirm`);
  if (view.status !== 'ready') throw new ApiError({ status: 422, code: 'photo_rejected', title: 'That photo didn’t work' });
  return view;
}
