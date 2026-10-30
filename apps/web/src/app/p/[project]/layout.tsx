"use client";

import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/app-shell";

export default function ProjectLayout({ children }: { children: ReactNode }) {
  const { project } = useParams<{ project: string }>();
  return <AppShell project={project}>{children}</AppShell>;
}
