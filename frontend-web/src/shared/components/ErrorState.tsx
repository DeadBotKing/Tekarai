/**
 * What a page shows when the API call failed.
 *
 * The habit this replaces is `.catch(() => setRows([]))`: a failed request
 * became an empty table, indistinguishable from "there is genuinely nothing
 * here". A warehouse with six parts and a warehouse the server could not
 * reach looked the same, and in demo mode the same failure was papered over
 * with fabricated rows. Both are worse than saying so.
 *
 * An error state is not decoration — it carries the retry, because the most
 * common cause is transient.
 */

import type { ReactNode } from "react";
import { Button } from "./primitives";
import { Icon } from "./Icon";

export interface ErrorStateProps {
  /** What the user was trying to see, in their words. */
  title?: string;
  /** Optional detail — the server's message, when it is fit to show. */
  detail?: string;
  /** Omit only when there is genuinely nothing to retry. */
  onRetry?: () => void;
  /** Extra actions, e.g. "go back". */
  children?: ReactNode;
  compact?: boolean;
}

export const ErrorState = ({
  title = "دریافت اطلاعات از سرور ناموفق بود",
  detail,
  onRetry,
  children,
  compact = false,
}: ErrorStateProps): JSX.Element => (
  <div
    className={compact ? "error-state error-state--compact" : "error-state"}
    role="alert"
    aria-live="polite"
  >
    <span className="error-state__icon" aria-hidden="true">
      <Icon name="warning" size={compact ? 18 : 26} />
    </span>
    <div className="error-state__body">
      <strong>{title}</strong>
      {detail ? <span className="error-state__detail">{detail}</span> : null}
      <span className="error-state__hint">
        این صفحه داده‌ی نمایشی جایگزین نمی‌کند؛ آنچه می‌بینید وضعیت واقعی ارتباط با سرور است.
      </span>
    </div>
    <div className="error-state__actions">
      {onRetry ? (
        <Button variant="secondary" size="sm" icon="refresh" onClick={onRetry}>
          تلاش دوباره
        </Button>
      ) : null}
      {children}
    </div>
  </div>
);
