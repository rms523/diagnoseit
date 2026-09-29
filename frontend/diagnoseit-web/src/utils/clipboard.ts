/**
 * Copying text to the clipboard, including where the modern API is not available.
 *
 * `navigator.clipboard` exists only in a secure context, so on a LAN deployment served over plain http
 * it is missing and the copy would silently do nothing. The hidden textarea is the fallback that works
 * there. Both paths can fail, so the caller is told whether the text was actually copied.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (window.isSecureContext && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the textarea, which often works where the clipboard API is blocked */
  }

  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    // Off-screen but still focusable: a hidden element cannot be selected.
    area.style.position = 'fixed';
    area.style.top = '0';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand('copy');
    document.body.removeChild(area);
    return copied;
  } catch {
    return false;
  }
}

/** Save text to a file the browser downloads. */
export function downloadText(text: string, filename: string, type = 'application/json'): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
