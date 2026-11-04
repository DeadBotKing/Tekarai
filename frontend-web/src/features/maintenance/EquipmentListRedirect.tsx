import { Navigate, useLocation } from "react-router-dom";

/** Keep old bookmarks, scan shortcuts, query strings and fragments working. */
export function EquipmentListRedirect(): JSX.Element {
  const location = useLocation();
  return <Navigate replace to={`/app/maintenance/equipment${location.search}${location.hash}`} />;
}
