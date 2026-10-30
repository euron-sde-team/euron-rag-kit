import type { Role } from "@/lib/types";

/** Editors and owners change data; only owners manage people, keys and the project. */
export const canEdit = (role: Role | undefined): boolean => role === "owner" || role === "editor";

export const isOwner = (role: Role | undefined): boolean => role === "owner";
