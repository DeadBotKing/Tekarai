// موج ۲ — بخش نگه‌داشته‌شده: رزرو قطعات روی درخواست کار
// (کنتور، تأمین‌کننده/پیش‌فاکتور و نسخه‌بندی سند به درخواست کاربر حذف شدند.)

export interface PartReservation {
  id: string;
  orderId: string;
  partCode: string;
  quantity: number;
  /** active = رزرو فعال، consumed = مصرف شد، released = آزاد شد */
  status: "active" | "consumed" | "released";
  at: string; // ISO
}

/** رزرو فعال یک قطعه در کل درخواست‌ها */
export const activeReservedForPart = (reservations: PartReservation[], partCode: string): number =>
  reservations
    .filter((reservation) => reservation.partCode === partCode && reservation.status === "active")
    .reduce((sum, reservation) => sum + reservation.quantity, 0);

/** موجودی آزاد = موجودی دسترس منها رزرو فعال (هرگز منفی نمی‌شود) */
export const availableStock = (quantityOnHand: number, reserved: number): number =>
  Math.max(0, quantityOnHand - reserved);

export const reservationsForOrder = (reservations: PartReservation[], orderId: string): PartReservation[] =>
  reservations.filter((reservation) => reservation.orderId === orderId && reservation.status === "active");
