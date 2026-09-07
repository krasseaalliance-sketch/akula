export const APP_BASE_PATH = process.env.NEXT_PUBLIC_APP_BASE_PATH ?? "/scout";
export const SCOUT_BASE_PATH = APP_BASE_PATH;
export const CORE_ROUTE = "/core";

export function appPath(path: string): string {
  if (path === "/") return APP_BASE_PATH;
  return `${APP_BASE_PATH}${path.startsWith("/") ? path : `/${path}`}`;
}

export const scoutPath = appPath;
export const corePath = () => appPath(CORE_ROUTE);
