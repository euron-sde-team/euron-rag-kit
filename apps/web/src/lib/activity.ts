import type { AuditEvent } from "@/lib/types";

const text = (value: unknown, fallback = ""): string =>
  typeof value === "string" || typeof value === "number" ? String(value) : fallback;

const PHRASES: Record<string, (d: Record<string, unknown>) => string> = {
  "project.created": () => "created the project",
  "project.updated": () => "updated the project details",
  "member.added": (d) => `added ${text(d.email, "a member")} as ${text(d.role, "a member")}`,
  "member.role_changed": (d) => `changed a member's role to ${text(d.role)}`,
  "member.removed": () => "removed a member",
  "collection.created": (d) => `created the collection ${text(d.slug)}`,
  "collection.updated": (d) => `updated the collection ${text(d.slug)}`.trim(),
  "collection.deleted": (d) => `deleted the collection ${text(d.slug)}`,
  "document.added": (d) => `added ${text(d.external_id, "a document")}`,
  "document.updated": () => "edited a document",
  "document.reprocessed": () => "reprocessed a document",
  "document.deleted": (d) => `deleted ${text(d.external_id, "a document")}`,
  "pipeline.created": (d) =>
    `created v${text(d.version)} of ${text(d.collection)}${d.index === "shared" ? " (reusing an index)" : ""}`,
  "pipeline.activated": (d) => `activated v${text(d.version)} of ${text(d.collection)}`,
  "dataset.created": (d) =>
    `created the dataset ${text(d.slug)} with ${text(d.items, "0")} questions`,
  "dataset.updated": () => "updated a dataset",
  "dataset.deleted": (d) => `deleted the dataset ${text(d.slug)}`,
  "dataset.items_imported": (d) =>
    `${d.replace ? "replaced the questions with" : "imported"} ${text(d.items, "some")} questions`,
  "dataset.item_deleted": () => "removed a dataset question",
  "eval_run.created": (d) => `started the run "${text(d.label)}" on ${text(d.dataset)}`,
  "eval_run.baseline_set": (d) => `set a new baseline for ${text(d.dataset)}`,
  "eval_run.deleted": () => "deleted an evaluation run",
  "api_key.created": (d) => `created the API key ${text(d.name)}`,
  "api_key.revoked": (d) => `revoked the API key ${text(d.name)}`,
};

/** "Priya Raman activated v2 of developer-docs": the actor plus a readable phrase. */
export function describeEvent(event: AuditEvent): { actor: string; phrase: string } {
  const phrase = PHRASES[event.action]?.(event.details) ?? event.action.replace(/[._]/g, " ");
  return { actor: event.actor ?? "An API key", phrase };
}
