// Write-time policy only. Do not use on login or existing account display.
const letters = 'آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیئؤءأإةيك'; // includes Arabic ي/ك for typo tolerance
const word = `[${letters}]+(?:[\\u200c-][${letters}]+)*`;
const fullName = new RegExp(`^(?:${word})(?: +${word})+$`, 'u');
const username = new RegExp(`^[${letters}](?:[${letters}۰-۹]|[._-](?=[${letters}۰-۹])|\\u200c(?=[${letters}]))*$`, 'u');
export const persianNameMessage = 'نام و نام خانوادگی را با حروف فارسی و با فاصله از هم وارد کنید؛ حروف لاتین و عدد مجاز نیست.';
export const persianUsernameMessage = 'نام کاربری الزامی است: ۳ تا ۶۴ نویسه، با حرف فارسی شروع شود؛ فقط حروف فارسی، ارقام فارسی، نقطه، خط تیره و زیرخط مجازند.';

function normalizeForValidation(value: string): string {
  return value
    .trim()
    // Strip invisible trailing ZWNJ (common artifact of Persian keyboards)
    .replace(/[\u200c\u200b\ufeff]+$/u, '')
    // Normalize Arabic ي/ك to Persian ی/ک to forgive keyboard layout mismatches
    .replace(/ي/g, 'ی').replace(/ك/g, 'ک');
}

export function persianNameError(value: string): string {
  const v = normalizeForValidation(value);
  return v.length >= 3 && v.length <= 160 && fullName.test(v) && !/[\r\n]/u.test(v) ? '' : persianNameMessage;
}
export function persianUsernameError(value: string): string {
  const v = normalizeForValidation(value);
  return v.length >= 3 && v.length <= 64 && username.test(v) && !/[\r\n]/u.test(v) ? '' : persianUsernameMessage;
}
export function persianAccountError(value: { displayName: string; username: string }): string {
  return persianNameError(value.displayName) || persianUsernameError(value.username);
}
/** Return a trimmed/normalized version for sending to the server. */
export function normalizePersianAccount<T extends { displayName: string; username: string }>(value: T): T {
  return { ...value, displayName: normalizeForValidation(value.displayName), username: normalizeForValidation(value.username) };
}
