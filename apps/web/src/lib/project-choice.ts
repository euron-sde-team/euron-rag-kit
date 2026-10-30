import type { ProjectSummary } from "@/lib/types";

/**
 * Where to land after sign-in: the project used last on this device when the person still
 * belongs to it, otherwise the one with the most collections (the list arrives sorted by
 * name, which would favour an empty project that happens to sort first).
 */
export function pickProject(projects: ProjectSummary[], last: string | null): string | null {
  if (last && projects.some((p) => p.slug === last)) return last;
  let best: ProjectSummary | null = null;
  for (const project of projects) {
    if (!best || project.collection_count > best.collection_count) best = project;
  }
  return best?.slug ?? null;
}
