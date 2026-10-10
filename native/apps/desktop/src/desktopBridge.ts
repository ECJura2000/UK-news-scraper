import { invoke as nativeInvoke, isTauri } from '@tauri-apps/api/core';
import { listen as nativeListen, type EventCallback } from '@tauri-apps/api/event';
import { save as nativeSave } from '@tauri-apps/plugin-dialog';
import { openPath as nativeOpenPath, openUrl as nativeOpenUrl } from '@tauri-apps/plugin-opener';

// The browser fixture is opt-in and cannot replace a native command or create artifacts.
export const designPreview = !isTauri() && new URLSearchParams(window.location.search).get('preview') === 'design';
const notice = (message: string) => window.dispatchEvent(new CustomEvent('preview-notice', { detail: message }));

export async function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (!designPreview) return nativeInvoke<T>(command, args);
  const { previewCommand } = await import('./designPreview');
  return previewCommand(command, args) as Promise<T>;
}
export async function listen<T>(name: string, callback: EventCallback<T>) {
  if (!designPreview) return nativeListen<T>(name, callback);
  const listener = (event: Event) => callback({ event: name, id: 0, payload: (event as CustomEvent<T>).detail });
  window.addEventListener(name, listener);
  return () => window.removeEventListener(name, listener);
}
export async function save(options: Parameters<typeof nativeSave>[0]) {
  if (!designPreview) return nativeSave(options);
  return window.prompt('設計預覽：變更示例檔名（不寫入檔案）', String(options?.defaultPath ?? '示例報表.xlsx'));
}
export async function openPath(path: string) {
  if (!designPreview) return nativeOpenPath(path);
  notice(`設計預覽：正式桌面版會開啟「${path.split(/[\\/]/).pop()}」。預覽不開啟或產生檔案。`);
}
export async function openUrl(url: string) {
  if (!designPreview) return nativeOpenUrl(url);
  window.open(url, '_blank', 'noopener,noreferrer');
}
