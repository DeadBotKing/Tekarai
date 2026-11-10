// Write-time policy only. Do not use on login or existing account display.
const letters = 'آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیئؤءأإة';
const word = `[${letters}]+(?:[\u200c-][${letters}]+)*`;
const fullName = new RegExp(`^(?:${word})(?: +${word})+$`, 'u');
const username = new RegExp(`^[${letters}](?:[${letters}۰-۹]|[._-](?=[${letters}۰-۹])|\u200c(?=[${letters}]))*$`, 'u');
export const persianNameMessage = 'نام و نام خانوادگی را با حروف فارسی و با فاصله از هم وارد کنید؛ حروف لاتین و عدد مجاز نیست.';
export const persianUsernameMessage = 'نام کاربری الزامی است: ۳ تا ۶۴ نویسه، با حرف فارسی شروع شود؛ فقط حروف فارسی، ارقام فارسی، نقطه، خط تیره و زیرخط مجازند.';
export function persianNameError(value:string):string { return value.length>=3 && value.length<=160 && fullName.test(value) && !/[\r\n]/u.test(value) ? '' : persianNameMessage; }
export function persianUsernameError(value:string):string { return value.length>=3 && value.length<=64 && username.test(value) && !/[\r\n]/u.test(value) ? '' : persianUsernameMessage; }
export function persianAccountError(value:{displayName:string;username:string}):string { return persianNameError(value.displayName)||persianUsernameError(value.username); }
