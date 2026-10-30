"use client";

import { useParams } from "next/navigation";

import { DocumentsTable } from "@/components/documents/documents-table";
import { useProject } from "@/lib/queries";
import { canEdit } from "@/lib/roles";

export default function CollectionDocumentsPage() {
  const { project, collection } = useParams<{ project: string; collection: string }>();
  const detail = useProject(project);
  return (
    <DocumentsTable
      project={project}
      collection={collection}
      editable={canEdit(detail.data?.role)}
    />
  );
}
