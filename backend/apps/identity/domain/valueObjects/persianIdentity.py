"""Write-time human identity policy. Never applied to login, hydration or legacy records."""
import re
from apps.sharedKernel.domain.errors import ValidationFailedError

LETTERS = 'آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیئؤءأإة'
WORD = '['+LETTERS+']+(?:[\u200c-]['+LETTERS+']+)*'
FULL_NAME = re.compile(WORD+'(?: +'+WORD+')+')
USERNAME = re.compile('['+LETTERS+'](?:['+LETTERS+'۰-۹]|[._-](?=['+LETTERS+'۰-۹])|\u200c(?=['+LETTERS+']))*')
NAME_MESSAGE = 'نام و نام خانوادگی را با حروف فارسی و با فاصله از هم وارد کنید؛ حروف لاتین و عدد مجاز نیست.'
USERNAME_MESSAGE = 'نام کاربری الزامی است: ۳ تا ۶۴ نویسه، با حرف فارسی شروع شود؛ فقط حروف فارسی، ارقام فارسی، نقطه، خط تیره و زیرخط مجازند.'

def validatePersianFullName(value):
    if not isinstance(value, str) or not 3 <= len(value) <= 160 or FULL_NAME.fullmatch(value) is None:
        raise ValidationFailedError(NAME_MESSAGE, fieldErrors={'displayName': NAME_MESSAGE})
    return value

def validatePersianUsername(value):
    if not isinstance(value, str) or not 3 <= len(value) <= 64 or USERNAME.fullmatch(value) is None:
        raise ValidationFailedError(USERNAME_MESSAGE, fieldErrors={'username': USERNAME_MESSAGE})
    return value
