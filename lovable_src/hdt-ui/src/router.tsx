import { QueryClient } from "@tanstack/react-query";
import { createHashHistory, createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { PageError } from "./components/hdt/page-error";
import { installDomGuard } from "./lib/dom-guard";

installDomGuard();

export const getRouter = () => {
  const queryClient = new QueryClient();

  const router = createRouter({
    routeTree,
    // Packaged build served by app.py uses hash URLs so refreshing any page keeps working.
    ...(import.meta.env.VITE_HASH_ROUTER === "1" && typeof window !== "undefined" ? { history: createHashHistory(), basepath: "/" } : {}),
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
    defaultErrorComponent: PageError,
  });

  return router;
};
