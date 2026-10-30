"use client";

import { useParams } from "next/navigation";
import type { ReactNode } from "react";

import { CollectionHeader } from "@/components/documents/collection-header";
import { PageBody } from "@/components/ui/page";

export default function CollectionLayout({ children }: { children: ReactNode }) {
  const { project, collection } = useParams<{ project: string; collection: string }>();
  return (
    <PageBody>
      <CollectionHeader project={project} collection={collection} />
      {children}
    </PageBody>
  );
}
